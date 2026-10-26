"""Durable research protocol state, independent of the upstream mining task map.

SQLite is the default; a PostgreSQL SQLAlchemy URL can be supplied in
``AQR_DATABASE_URL``.  Conditional updates enforce the freeze/finalize boundary
across threads and application processes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Column, MetaData, String, Table, create_engine, select, update


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def plain(value: Any) -> Any:
    """Convert scientific result types to JSON, retaining missing metrics as null."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "item"):
        return plain(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Result contains a non-serializable {type(value).__name__}")


class StateConflict(ValueError):
    pass


class ResearchStore:
    def __init__(self, data_root: str | Path, database_url: str | None = None):
        self.data_root = Path(data_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.database_url = database_url or f"sqlite:///{self.data_root / 'research.sqlite3'}"
        kwargs = {"connect_args": {"check_same_thread": False, "timeout": 30}} if self.database_url.startswith("sqlite") else {}
        self.engine = create_engine(self.database_url, future=True, **kwargs)
        meta = MetaData()
        self.protocols = Table(
            "research_protocols", meta,
            Column("id", String(64), primary_key=True),
            Column("state", String(40), nullable=False),
            Column("document", JSON, nullable=False),
            Column("result", JSON),
            Column("frozen_candidate", JSON),
            Column("active_task_id", String(64)),
            Column("created_at", String(48), nullable=False),
            Column("updated_at", String(48), nullable=False),
        )
        self.tasks = Table(
            "research_tasks", meta,
            Column("id", String(64), primary_key=True),
            Column("protocol_id", String(64), nullable=False, index=True),
            Column("status", String(40), nullable=False),
            Column("document", JSON, nullable=False),
            Column("created_at", String(48), nullable=False),
            Column("updated_at", String(48), nullable=False),
        )
        self.memories = Table(
            "research_memories", meta,
            Column("id", String(64), primary_key=True),
            Column("dataset_fingerprint", String(256), nullable=False, index=True),
            Column("protocol_id", String(64), nullable=False),
            Column("document", JSON, nullable=False),
            Column("created_at", String(48), nullable=False),
        )
        meta.create_all(self.engine)

    def create_protocol(self, document: dict) -> dict:
        document = plain(copy.deepcopy(document))
        protocol_id = str(uuid.uuid4())
        document["id"] = protocol_id
        now = utc_now()
        with self.engine.begin() as conn:
            conn.execute(self.protocols.insert().values(
                id=protocol_id, state="draft", document=document, result=None,
                frozen_candidate=None, active_task_id=None, created_at=now, updated_at=now,
            ))
        return self.get_protocol(protocol_id)

    def get_protocol(self, protocol_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(self.protocols).where(self.protocols.c.id == protocol_id)).mappings().first()
        if row is None:
            return None
        result = dict(row)
        result["protocol"] = result.pop("document")
        result["name"] = result["protocol"].get("name", protocol_id)
        task_id = result.get("active_task_id")
        result["task"] = self.get_task(task_id) if task_id else None
        return result

    def list_protocols(self) -> list[dict]:
        with self.engine.connect() as conn:
            ids = conn.execute(select(self.protocols.c.id).order_by(self.protocols.c.created_at.desc())).scalars().all()
        return [self.get_protocol(protocol_id) for protocol_id in ids]

    def get_task(self, task_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(self.tasks).where(self.tasks.c.id == task_id)).mappings().first()
        if row is None:
            return None
        return {**row["document"], "id": row["id"], "protocol_id": row["protocol_id"],
                "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def start_task(self, protocol_id: str, config: dict, purpose: str = "research") -> dict:
        task_id = str(uuid.uuid4())
        now = utc_now()
        if purpose == "finalize":
            allowed, state = ["frozen"], "finalizing"
        else:
            allowed, state = ["draft", "researched", "failed", "interrupted"], "running"
        document = {"purpose": purpose, "config": plain(config), "events": [], "result": None,
                    "error": None, "run_dir": str(self.data_root / "runs" / task_id)}
        with self.engine.begin() as conn:
            claimed = conn.execute(update(self.protocols).where(
                self.protocols.c.id == protocol_id, self.protocols.c.state.in_(allowed),
            ).values(state=state, active_task_id=task_id, updated_at=now))
            if claimed.rowcount != 1:
                raise StateConflict("Protocol is busy, frozen, already finalized, or not ready for this operation")
            conn.execute(self.tasks.insert().values(id=task_id, protocol_id=protocol_id,
                status="queued", document=document, created_at=now, updated_at=now))
        Path(document["run_dir"]).mkdir(parents=True, exist_ok=True)
        return self.get_task(task_id)

    def update_task(self, task_id: str, *, status: str | None = None, event: dict | None = None,
                    result: dict | None = None, error: str | None = None) -> dict:
        with self.engine.begin() as conn:
            row = conn.execute(select(self.tasks).where(self.tasks.c.id == task_id)).mappings().one()
            document = copy.deepcopy(row["document"])
            if event is not None:
                event = plain(event)
                event.setdefault("timestamp", utc_now())
                document["events"] = (document.get("events", []) + [event])[-1000:]
            if result is not None:
                document["result"] = plain(result)
            if error is not None:
                document["error"] = error
            conn.execute(update(self.tasks).where(self.tasks.c.id == task_id).values(
                status=status or row["status"], document=document, updated_at=utc_now()))
        return self.get_task(task_id)

    def claim_task(self, task_id: str) -> bool:
        """CAS protects against duplicate queue deliveries across worker processes."""
        with self.engine.begin() as conn:
            changed = conn.execute(update(self.tasks).where(
                self.tasks.c.id == task_id, self.tasks.c.status == "queued",
            ).values(status="running", updated_at=utc_now()))
            return changed.rowcount == 1

    def finish_task(self, task_id: str, result: dict | None = None, error: str | None = None) -> None:
        task = self.get_task(task_id)
        purpose = task["purpose"]
        status = "failed" if error else "completed"
        self.update_task(task_id, status=status, result=result, error=error)
        next_state = ("finalization_failed" if error else "finalized") if purpose == "finalize" else ("failed" if error else "researched")
        values = {"state": next_state, "updated_at": utc_now()}
        if result is not None:
            values["result"] = plain(result)
        with self.engine.begin() as conn:
            conn.execute(update(self.protocols).where(
                self.protocols.c.id == task["protocol_id"], self.protocols.c.active_task_id == task_id,
            ).values(**values))
        # A held-out observation must never enter the reusable planning memory.
        if result is not None and purpose == "research":
            protocol = self.get_protocol(task["protocol_id"])["protocol"]
            self.save_memories(task["protocol_id"], protocol["dataset_fingerprint"], result.get("memories", []))

    def freeze(self, protocol_id: str, candidate_id: str) -> dict:
        entry = self.get_protocol(protocol_id)
        if entry is None:
            raise KeyError(protocol_id)
        result = copy.deepcopy(entry.get("result") or {})
        candidates = result.get("trials", [])
        candidate = next((c for c in candidates if str(c.get("id", c.get("candidate_id", ""))) == candidate_id), None)
        best = result.get("best_candidate")
        if candidate is None and isinstance(best, dict) and str(best.get("id", best.get("candidate_id", ""))) == candidate_id:
            candidate = best
        if candidate is None:
            raise ValueError("Candidate does not belong to the latest completed research run")
        if candidate.get("status") in {"failed", "invalid", "error"}:
            raise ValueError("A failed candidate cannot be frozen")
        selected = candidate.get("candidate", candidate)
        signature = hashlib.sha256(json.dumps(plain(selected), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        frozen = {"candidate_id": candidate_id, "candidate_hash": signature,
                  "candidate": plain(selected), "frozen_at": utc_now()}
        result["best_candidate"] = plain(selected)
        if candidate.get("evaluation"):
            result["validation"] = plain(candidate["evaluation"])
        result["frozen_candidate"] = frozen
        with self.engine.begin() as conn:
            changed = conn.execute(update(self.protocols).where(
                self.protocols.c.id == protocol_id, self.protocols.c.state == "researched",
            ).values(state="frozen", frozen_candidate=frozen, result=plain(result), updated_at=utc_now()))
            if changed.rowcount != 1:
                raise StateConflict("Only a completed, unfrozen research run can freeze a candidate")
        return self.get_protocol(protocol_id)

    def save_memories(self, protocol_id: str, fingerprint: str, memories: list[dict]) -> None:
        with self.engine.begin() as conn:
            for memory in memories:
                memory = plain(memory)
                if memory.get("source_split") != "validation" or memory.get("context", {}).get("purpose") != "validation":
                    continue
                memory["dataset_fingerprint"] = fingerprint
                identity = memory.get("id") or json.dumps(memory, sort_keys=True, ensure_ascii=False)
                key = hashlib.sha256((fingerprint + identity).encode()).hexdigest()
                if conn.execute(select(self.memories.c.id).where(self.memories.c.id == key)).first():
                    continue
                conn.execute(self.memories.insert().values(id=key, dataset_fingerprint=fingerprint,
                    protocol_id=protocol_id, document=memory, created_at=utc_now()))

    def list_memories(self, fingerprint: str | None = None) -> list[dict]:
        query = select(self.memories).order_by(self.memories.c.created_at.desc())
        if fingerprint:
            query = query.where(self.memories.c.dataset_fingerprint == fingerprint)
        with self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        return [{**row["document"], "store_id": row["id"], "protocol_id": row["protocol_id"]} for row in rows]

    def recover_interrupted(self) -> int:
        """Processes are not restored from snapshots; never re-run a claimed test."""
        count = 0
        with self.engine.begin() as conn:
            rows = conn.execute(select(self.protocols).where(self.protocols.c.state.in_(["running", "finalizing"]))).mappings().all()
            for row in rows:
                state = "finalization_failed" if row["state"] == "finalizing" else "interrupted"
                conn.execute(update(self.protocols).where(self.protocols.c.id == row["id"]).values(state=state, updated_at=utc_now()))
                task_id = row["active_task_id"]
                task = conn.execute(select(self.tasks).where(self.tasks.c.id == task_id)).mappings().first()
                if task:
                    document = copy.deepcopy(task["document"])
                    document["error"] = "Application restarted before task completion; final holdout claims are never automatically retried"
                    conn.execute(update(self.tasks).where(self.tasks.c.id == task_id).values(status="interrupted", document=document, updated_at=utc_now()))
                count += 1
        return count

