"""Shared task executor, using the existing RQ library for optional Redis jobs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .store import ResearchStore, plain


def _persist_failed_research_memories(store, task):
    """A failed experiment must not discard already committed validation evidence."""
    if task["purpose"] != "research":
        return
    from .memory import EconomicMemoryStore
    protocol = store.get_protocol(task["protocol_id"])["protocol"]
    records = []
    for branch in ("with_memory", "without_memory"):
        path = Path(task["run_dir"]) / branch / "memory.sqlite"
        if path.is_file():
            with EconomicMemoryStore(path) as observations:
                records.extend(observations.list(limit=1000))
    store.save_memories(task["protocol_id"], protocol["dataset_fingerprint"], records)


def execute_task(task_id: str, data_root: str | None = None, *, store: ResearchStore | None = None):
    store = store or ResearchStore(data_root or os.getenv("AQR_DATA_DIR", "data/results/research"), os.getenv("AQR_DATABASE_URL"))
    task = store.get_task(task_id)
    if task is None:
        raise ValueError("Queued task no longer exists")
    if task["status"] != "queued":
        # A duplicated delivery must never execute the held-out test twice.
        return {"status": "ignored", "reason": "task already claimed"}
    if not store.claim_task(task_id):
        return {"status": "ignored", "reason": "task already claimed"}
    entry = store.get_protocol(task["protocol_id"])
    protocol = entry["protocol"]
    config = dict(task["config"])
    config.update(output_dir=task["run_dir"], run_dir=task["run_dir"])
    config["initial_memories"] = store.list_memories(protocol["dataset_fingerprint"]) if config.get("use_memory") else []
    try:
        from .experiment import finalize_research, run_research
        if task["purpose"] == "finalize":
            result = finalize_research(protocol, entry["result"], config)
        else:
            result = run_research(protocol, config, lambda event: store.update_task(task_id, event=event))
        result = plain(result)
        if task["purpose"] == "research" and result.get("holdout") is not None:
            raise ValueError("Research execution returned a sealed holdout result")
        artifact = Path(task["run_dir"]) / "result.json"
        artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        store.finish_task(task_id, result=result)
        return {"status": "completed", "task_id": task_id}
    except Exception as error:
        _persist_failed_research_memories(store, task)
        store.finish_task(task_id, error=f"{type(error).__name__}: {error}")
        return {"status": "failed", "task_id": task_id}


def on_job_failure(job, connection, error_type, error, traceback):
    """RQ timeout/process failures must become durable experiment failures."""
    store = ResearchStore(job.args[1], os.getenv("AQR_DATABASE_URL"))
    task = store.get_task(job.args[0])
    if task and task["status"] not in ("completed", "failed"):
        _persist_failed_research_memories(store, task)
        store.finish_task(task["id"], error=f"RQ worker terminated: {error_type.__name__}")


def main():
    parser = argparse.ArgumentParser(description="Redis/RQ research worker")
    parser.add_argument("--burst", action="store_true", help="Process queued jobs and exit")
    args = parser.parse_args()
    endpoint = os.getenv("AQR_REDIS_URL")
    if not endpoint:
        parser.error("AQR_REDIS_URL is required for a Redis worker")
    from redis import Redis
    from rq import Queue, Worker
    connection = Redis.from_url(endpoint)
    queue = Queue(os.getenv("AQR_QUEUE_NAME", "aqr-research"), connection=connection)
    Worker([queue], connection=connection).work(burst=args.burst)


if __name__ == "__main__":
    main()
