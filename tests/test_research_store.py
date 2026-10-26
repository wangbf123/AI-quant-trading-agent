from concurrent.futures import ThreadPoolExecutor

import pytest

from quantaalpha.research.store import ResearchStore, StateConflict


def completed(store):
    entry = store.create_protocol({"name": "unit", "dataset_fingerprint": "fixture"})
    task = store.start_task(entry["id"], {"budget": 2})
    candidate = {"id": "candidate-01", "topk": 3}
    result = {"trials": [{"id": "candidate-01", "candidate": candidate, "status": "completed", "evaluation": {"metrics": {"annualized_return": -0.01}}}], "best_candidate": candidate, "holdout": None, "memories": []}
    store.finish_task(task["id"], result=result)
    return entry["id"]


def test_atomic_finalization_allows_exactly_one_claim(tmp_path):
    store = ResearchStore(tmp_path)
    protocol = completed(store)
    with pytest.raises(StateConflict):
        store.start_task(protocol, {}, "finalize")
    frozen = store.freeze(protocol, "candidate-01")
    assert frozen["state"] == "frozen"
    assert frozen["result"]["validation"]["metrics"]["annualized_return"] == -0.01

    def attempt(_):
        try:
            return store.start_task(protocol, {}, "finalize")["id"]
        except StateConflict:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(attempt, range(4)))
    assert sum(item is not None for item in claims) == 1
    task_id = next(item for item in claims if item)
    store.finish_task(task_id, result={"holdout": {"metrics": {}}, "memories": [{"source_split": "holdout"}]})
    assert store.list_memories() == []
    with pytest.raises(StateConflict):
        store.start_task(protocol, {}, "finalize")
    with pytest.raises(StateConflict):
        store.start_task(protocol, {})


def test_restart_never_retries_an_interrupted_holdout(tmp_path):
    store = ResearchStore(tmp_path)
    protocol = completed(store)
    store.freeze(protocol, "candidate-01")
    store.start_task(protocol, {}, "finalize")
    restored = ResearchStore(tmp_path)
    assert restored.recover_interrupted() == 1
    assert restored.get_protocol(protocol)["state"] == "finalization_failed"
    with pytest.raises(StateConflict):
        restored.start_task(protocol, {}, "finalize")
