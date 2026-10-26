import copy

import pytest

from quantaalpha.research.experiment import create_demo_protocol, demo_candidate, run_research, validate_candidate


def test_memory_changes_next_proposal_without_changing_costs():
    without, _ = demo_candidate(1, 42, [])
    with_memory, reasoning = demo_candidate(1, 42, [{"category": "cost_drag"}, {"category": "negative_net_return"}])
    assert with_memory != without
    assert with_memory["n_drop"] == 1
    assert "成本" in reasoning
    assert "open_cost" not in with_memory


@pytest.mark.parametrize("changes", [{"topk": True}, {"n_drop": 100}, {"feature_names": ["__import__('os')", "$close"]}, {"family": "arbitrary_python"}])
def test_llm_candidates_are_bounded_and_registered(changes):
    base = {"family": "momentum", "topk": 3, "n_drop": 1, **changes}
    with pytest.raises(ValueError):
        validate_candidate(base)


def test_equal_budget_branches_never_evaluate_final_test(monkeypatch, tmp_path):
    import quantaalpha.research.experiment as module
    protocol = create_demo_protocol(tmp_path / "fixture")
    calls = []

    def evaluate(base, selected_protocol, candidate, directory, purpose, seed):
        calls.append(purpose)
        return {"metrics": {"gross_annualized_return": 0.1, "annualized_return": -0.01, "information_ratio": -0.5, "max_drawdown": -0.02}, "equity": [], "diagnostics": {"duration_ms": 1}}

    monkeypatch.setattr(module, "_run_candidate", evaluate)
    result = run_research(protocol, {"budget": 3, "seed": 42, "use_memory": True, "run_ablation": True, "output_dir": str(tmp_path / "runs")})
    assert calls == ["research"] * 6
    assert result["holdout"] is None
    assert result["provenance"]["holdout_accessed"] is False
    assert result["ablation"]["with_memory"]["evaluations"] == 3
    assert result["ablation"]["without_memory"]["evaluations"] == 3
    assert result["trials"][1]["retrieved_memory_ids"]
    assert not result["ablation"]["without_memory"]["trials"][1]["retrieved_memory_ids"]
