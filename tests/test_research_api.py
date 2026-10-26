import copy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantaalpha.research.store import ResearchStore
from research_api import create_research_router


def test_api_research_freeze_finalize_and_export(monkeypatch, tmp_path):
    import quantaalpha.research.experiment as experiment
    candidate = {"id": "candidate-01", "family": "momentum", "topk": 3}
    result = {"trials": [{"id": "candidate-01", "candidate": candidate, "status": "completed", "evaluation": {"metrics": {"annualized_return": -0.1}}}], "best_candidate": candidate, "validation": {}, "holdout": None, "memories": [], "provenance": {"source": "synthetic"}}
    monkeypatch.setattr(experiment, "run_research", lambda *args: copy.deepcopy(result))

    def finalize(protocol, prior, config):
        value = copy.deepcopy(prior)
        value["holdout"] = {"metrics": {"annualized_return": -0.02}}
        return value

    monkeypatch.setattr(experiment, "finalize_research", finalize)
    store = ResearchStore(tmp_path / "store")
    application = FastAPI()
    application.include_router(create_research_router(tmp_path, store=store, synchronous=True))
    with TestClient(application) as client:
        response = client.post('/api/v1/research/demo', json={"budget": 2})
        assert response.status_code == 200, response.text
        protocol_id = response.json()["data"]["protocol"]["id"]
        path = f'/api/v1/research/protocols/{protocol_id}'
        entry = client.get(path).json()["data"]["protocol"]
        assert entry["state"] == "researched"
        assert entry["result"]["holdout"] is None
        assert client.post(path + '/finalize').status_code == 409
        assert client.post(path + '/freeze', json={"candidate_id": "unknown"}).status_code == 422
        assert client.post(path + '/freeze', json={"candidate_id": "candidate-01"}).status_code == 200
        assert client.post(path + '/finalize').status_code == 200
        assert client.post(path + '/finalize').status_code == 409
        exported = client.get(path + '/export')
        assert exported.status_code == 200
        assert exported.json()["state"] == "finalized"
        assert exported.json()["result"]["holdout"] is not None
        assert client.get('/api/v1/research/memories').json()["data"]["memories"] == []


def test_bad_window_request_and_missing_model_binding_are_explicit(monkeypatch, tmp_path):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('AQR_LLM_API_KEY', raising=False)
    application = FastAPI()
    application.include_router(create_research_router(tmp_path, store=ResearchStore(tmp_path), synchronous=True))
    with TestClient(application) as client:
        assert client.post('/api/v1/research/protocols', json={"name": "incomplete"}).status_code == 422
        assert client.post('/api/v1/research/demo', json={"budget": 2, "planner": "llm"}).status_code == 422
