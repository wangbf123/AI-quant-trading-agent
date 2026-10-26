"""Additive research-governance API for the existing QuantaAlpha dashboard."""

from __future__ import annotations

import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from quantaalpha.research.store import ResearchStore, StateConflict, plain, utc_now


class ProtocolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    dataset_fingerprint: str = Field(min_length=1, max_length=256)
    train: list[str] = Field(min_length=2, max_length=2)
    tune: list[str] = Field(min_length=2, max_length=2)
    validation: list[str] = Field(min_length=2, max_length=2)
    holdout: list[str] = Field(min_length=2, max_length=2)
    purge_sessions: int = Field(default=2, ge=2, le=100)
    config_path: str | None = None
    data_root: str | None = None
    calendar: list[str] | None = None
    costs: dict[str, Any] | None = None
    strategy: dict[str, Any] | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    budget: int = Field(default=4, ge=2, le=20)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    use_memory: bool = True
    run_ablation: bool = False
    planner: Literal["demo", "llm"] = "demo"
    objective: str = Field(default="Discover robust daily factors after transaction costs", max_length=4000)


class FreezeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(min_length=1, max_length=200)


def _capabilities(store: ResearchStore) -> dict:
    def available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            return False
    return {
        "llm_configured": bool(os.getenv("OPENAI_API_KEY") or os.getenv("AQR_LLM_API_KEY")),
        "llm_protocol": os.getenv("AQR_LLM_PROTOCOL", "openai"),
        "llm_model": os.getenv("AQR_LLM_MODEL") or os.getenv("CHAT_MODEL", "step-5-preview"),
        "qlib": available("qlib"), "torch": available("torch"),
        "native_execution": False,
        "postgres": store.database_url.startswith("postgresql"),
        "redis": bool(os.getenv("AQR_REDIS_URL")),
        "job_backend": "redis_rq" if os.getenv("AQR_REDIS_URL") else "local_thread",
    }


def create_research_router(project_root: Path, store: ResearchStore | None = None,
                           synchronous: bool = False) -> APIRouter:
    data_root = Path(os.getenv("AQR_DATA_DIR", str(project_root / "data" / "results" / "research")))
    store = store or ResearchStore(data_root, os.getenv("AQR_DATABASE_URL"))
    router = APIRouter(prefix="/api/v1/research", tags=["Research protocols"])
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="quantaalpha-research")
    router.research_store = store

    @router.on_event("startup")
    def recover():
        if not os.getenv("AQR_REDIS_URL"):
            store.recover_interrupted()

    @router.on_event("shutdown")
    def shutdown():
        executor.shutdown(wait=False, cancel_futures=True)

    def entry_or_404(protocol_id: str) -> dict:
        entry = store.get_protocol(protocol_id)
        if entry is None:
            raise HTTPException(404, "Research protocol not found")
        return entry

    def execute(task_id: str):
        from quantaalpha.research.jobs import execute_task
        return execute_task(task_id, store=store)

    def launch(protocol_id: str, request: RunRequest, purpose: str = "research") -> dict:
        entry_or_404(protocol_id)
        if purpose != "finalize" and request.planner == "llm" and not _capabilities(store)["llm_configured"]:
            raise HTTPException(422, "LLM planner requires an API binding in environment settings")
        try:
            task = store.start_task(protocol_id, request.model_dump(), purpose)
        except StateConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        if synchronous:
            execute(task["id"])
        elif os.getenv("AQR_REDIS_URL"):
            try:
                from redis import Redis
                from rq import Queue
                connection = Redis.from_url(os.environ["AQR_REDIS_URL"], socket_connect_timeout=3, socket_timeout=3)
                connection.ping()
                queue = Queue(os.getenv("AQR_QUEUE_NAME", "aqr-research"), connection=connection)
                queue.enqueue("quantaalpha.research.jobs.execute_task", task["id"], str(store.data_root),
                              job_timeout=3600, result_ttl=86400,
                              on_failure="quantaalpha.research.jobs.on_job_failure")
            except Exception as exc:
                store.finish_task(task["id"], error=f"Redis queue unavailable: {type(exc).__name__}")
                raise HTTPException(503, "Redis queue unavailable; task was not silently moved to local execution") from None
        else:
            executor.submit(execute, task["id"])
        return store.get_task(task["id"])

    @router.get("/overview")
    def overview():
        return {"success": True, "data": {"protocols": store.list_protocols(),
                "memories": store.list_memories(), "capabilities": _capabilities(store)}}

    @router.post("/protocols")
    def create_protocol(request: ProtocolRequest):
        from quantaalpha.research.protocol import validate_protocol
        payload = request.model_dump(exclude_none=True)
        calendar = payload.pop("calendar", None)
        try:
            normalized = validate_protocol(payload, calendar=calendar)
            entry = store.create_protocol(normalized)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"success": True, "data": {"protocol": entry}}

    @router.get("/protocols/{protocol_id}")
    def get_protocol(protocol_id: str):
        return {"success": True, "data": {"protocol": entry_or_404(protocol_id)}}

    @router.post("/protocols/{protocol_id}/run")
    def run_protocol(protocol_id: str, request: RunRequest):
        return {"success": True, "data": {"task": launch(protocol_id, request)}}

    @router.post("/protocols/{protocol_id}/freeze")
    def freeze_protocol(protocol_id: str, request: FreezeRequest):
        entry_or_404(protocol_id)
        try:
            entry = store.freeze(protocol_id, request.candidate_id)
        except StateConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"success": True, "data": {"protocol": entry}}

    @router.post("/protocols/{protocol_id}/finalize")
    def finalize_protocol(protocol_id: str):
        entry = entry_or_404(protocol_id)
        prior_config = (entry.get("task") or {}).get("config", {})
        request = RunRequest.model_validate(prior_config)
        return {"success": True, "data": {"task": launch(protocol_id, request, "finalize")}}

    @router.get("/protocols/{protocol_id}/export")
    def export_protocol(protocol_id: str):
        entry = entry_or_404(protocol_id)
        document = {"schema_version": "1.0", "exported_at": utc_now(),
                    "protocol": entry["protocol"], "state": entry["state"],
                    "frozen_candidate": entry["frozen_candidate"], "result": entry["result"],
                    "task": entry["task"], "capabilities": _capabilities(store)}
        return JSONResponse(plain(document), headers={"Content-Disposition": f'attachment; filename="research-{protocol_id}.json"'})

    @router.get("/memories")
    def get_memories(dataset_fingerprint: str | None = None):
        return {"success": True, "data": {"memories": store.list_memories(dataset_fingerprint)}}

    @router.post("/demo")
    def create_demo(request: RunRequest):
        from quantaalpha.research.experiment import create_demo_protocol
        from quantaalpha.research.protocol import validate_protocol
        try:
            demo = create_demo_protocol(store.data_root / "demo")
            protocol = validate_protocol(demo)
            entry = store.create_protocol(protocol)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        task = launch(entry["id"], request)
        return {"success": True, "data": {"protocol": store.get_protocol(entry["id"]), "task": task}}

    return router


router = create_research_router(Path(__file__).resolve().parents[2])
