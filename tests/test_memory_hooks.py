import json
from types import SimpleNamespace

import pytest

from quantaalpha.research.memory import EconomicMemoryStore, MemoryProtocolError


def setup_context(monkeypatch, tmp_path, purpose="validation"):
    context = {"dataset_fingerprint": "test-data", "execution_fingerprint": "test-costs",
               "validation_window": ["2021-01-01", "2021-12-31"], "purpose": purpose}
    path = tmp_path / "context.json"
    path.write_text(json.dumps(context))
    monkeypatch.setenv("AQR_RESEARCH_CONTEXT", str(path))
    monkeypatch.setenv("AQR_MEMORY_PATH", str(tmp_path / "memory.sqlite"))
    return context


def test_generator_keeps_upstream_context_and_injects_only_validation_evidence(monkeypatch, tmp_path):
    from quantaalpha.research import hooks
    context = setup_context(monkeypatch, tmp_path)
    with EconomicMemoryStore(hooks.memory_path()) as store:
        store.record(context, {"gross_return": 0.1, "net_return": -0.1}, {"name": "factor-a"})
    calls = []

    def original(self, trace, history_limit):
        calls.append((trace, history_limit))
        return {"RAG": "existing upstream evidence", "hypothesis_and_feedback": "unchanged"}, True

    monkeypatch.setattr(hooks.AlphaAgentHypothesisGen, "prepare_context", original)
    instance = hooks.MemoryAwareHypothesisGen.__new__(hooks.MemoryAwareHypothesisGen)
    sentinel = object()
    result, json_mode = instance.prepare_context(sentinel, 3)
    assert calls == [(sentinel, 3)]
    assert result["hypothesis_and_feedback"] == "unchanged"
    assert "existing upstream evidence" in result["RAG"]
    assert "cost_drag" in result["RAG"]
    assert "no final-test access" in result["RAG"]
    assert json_mode is True
    # Actual generation remains the upstream implementation.
    assert hooks.MemoryAwareHypothesisGen.gen is hooks.AlphaAgentHypothesisGen.gen


def test_feedback_preserves_upstream_result_and_records_economic_evidence(monkeypatch, tmp_path):
    from quantaalpha.research import hooks
    setup_context(monkeypatch, tmp_path)
    feedback = SimpleNamespace(observations="upstream feedback")
    seen = []

    def original(self, exp, hypothesis, trace):
        seen.append((exp, hypothesis, trace))
        return feedback

    monkeypatch.setattr(hooks.AlphaAgentQlibFactorHypothesisExperiment2Feedback, "generate_feedback", original)
    instance = hooks.MemoryAwareFeedback.__new__(hooks.MemoryAwareFeedback)
    experiment = SimpleNamespace(result={"net_return": -0.02, "gross_return": 0.05}, sub_tasks=[])
    result = instance.generate_feedback(experiment, "hypothesis", "trace")
    assert result is feedback
    assert seen == [(experiment, "hypothesis", "trace")]
    assert result.observations == "upstream feedback"
    assert "cost_drag" in result.economic_failure_tags
    with EconomicMemoryStore(hooks.memory_path()) as store:
        assert len(store.list()) == 2


def test_unconfigured_hook_explicitly_warns_and_preserves_no_memory_behavior(monkeypatch):
    from quantaalpha.research import hooks
    monkeypatch.delenv("AQR_RESEARCH_CONTEXT", raising=False)
    monkeypatch.setattr(hooks.AlphaAgentHypothesisGen, "prepare_context", lambda *args: ({"RAG": None}, True))
    instance = hooks.MemoryAwareHypothesisGen.__new__(hooks.MemoryAwareHypothesisGen)
    with pytest.warns(RuntimeWarning, match="disabled"):
        result, _ = instance.prepare_context(object())
    assert result["RAG"] is None
    assert instance.last_retrieved_memories == []


def test_holdout_hook_rejected_before_upstream_feedback_call(monkeypatch, tmp_path):
    from quantaalpha.research import hooks
    setup_context(monkeypatch, tmp_path, purpose="holdout")
    called = []
    monkeypatch.setattr(hooks.AlphaAgentQlibFactorHypothesisExperiment2Feedback, "generate_feedback",
                        lambda *args: called.append(True))
    instance = hooks.MemoryAwareFeedback.__new__(hooks.MemoryAwareFeedback)
    with pytest.raises(MemoryProtocolError):
        instance.generate_feedback(SimpleNamespace(result={}), None, None)
    assert called == []
