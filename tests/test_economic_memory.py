from concurrent.futures import ThreadPoolExecutor

import pytest

from quantaalpha.research.memory import EconomicMemoryStore, MemoryProtocolError, normalize_result_metrics


def context(**changes):
    return {
        "dataset_fingerprint": "dataset-v1", "execution_fingerprint": "costs-v1",
        "validation_window": ["2021-01-01", "2021-12-31"],
        "holdout_window": ["2022-01-01", "2023-12-31"], "purpose": "validation", **changes,
    }


def test_records_only_supported_economic_failures_and_persists(tmp_path):
    path = tmp_path / "memory.sqlite"
    metrics = {"gross_return": 0.08, "net_return": -0.02, "max_drawdown": -0.2,
               "subperiod_returns": [0.04, -0.05, 0.02]}
    with EconomicMemoryStore(path) as store:
        records = store.record(context(), metrics, {"family": "momentum", "name": "m20"})
        assert {r["category"] for r in records} == {
            "cost_drag", "negative_net_return", "high_drawdown", "regime_instability",
        }
        assert all(r["evidence"]["source_split"] == "validation" for r in records)
        store.record(context(), metrics, {"family": "momentum", "name": "m20"})
        assert len(store.list()) == 4
    with EconomicMemoryStore(path) as restored:
        assert len(restored.retrieve(context())) == 4


def test_memory_isolated_by_dataset_execution_and_validation_window(tmp_path):
    with EconomicMemoryStore(tmp_path / "memory.sqlite") as store:
        store.record(context(), {"net_return": -0.1}, {"family": "momentum"})
        assert store.retrieve(context())
        assert store.retrieve(context(dataset_fingerprint="different")) == []
        assert store.retrieve(context(execution_fingerprint="different")) == []
        assert store.retrieve(context(validation_window=["2020-01-01", "2020-12-31"])) == []


@pytest.mark.parametrize("purpose", [None, "test", "holdout", "final_test"])
def test_final_test_and_missing_purpose_are_rejected(tmp_path, purpose):
    with EconomicMemoryStore(tmp_path / "memory.sqlite") as store:
        with pytest.raises(MemoryProtocolError):
            store.record(context(purpose=purpose), {"net_return": -1}, {})
        assert store.list() == []


def test_explicit_final_test_source_and_overlapping_windows_are_rejected(tmp_path):
    with EconomicMemoryStore(tmp_path / "memory.sqlite") as store:
        for metrics, source in (({"net_return": -1}, "test"),
                                ({"net_return": -1, "source_split": "holdout"}, "validation")):
            with pytest.raises(MemoryProtocolError):
                store.record(context(), metrics, {}, source=source)
        with pytest.raises(MemoryProtocolError, match="overlap"):
            store.record(context(holdout_window=["2021-12-01", "2022-12-31"]), {}, {})


def test_missing_cost_and_subperiod_data_are_not_fabricated(tmp_path):
    with EconomicMemoryStore(tmp_path / "memory.sqlite") as store:
        # A gross loss alone must not become a negative *net* return finding.
        assert store.record(context(), {"gross_return": -0.05}, {}) == []
        records = store.record(context(), {"net_return": -0.05}, {})
        assert [r["category"] for r in records] == ["negative_net_return"]
        assert "gross_return" not in records[0]["metrics"]
        assert "subperiod_returns" not in records[0]["metrics"]


def test_qllib_net_metrics_take_precedence_and_return_bases_never_mix():
    result = normalize_result_metrics({
        "1day.excess_return_with_cost.annualized_return": -0.03,
        "1day.excess_return_without_cost.annualized_return": 0.08,
        "annualized_return": 0.50, "total_return": 0.2,
    })
    assert result["net_return"] == -0.03
    assert result["gross_return"] == 0.08
    assert result["return_basis"] == "annualized"
    mixed = normalize_result_metrics({"net_return": 0.1, "gross_annualized_return": 0.7})
    assert mixed["net_return"] == 0.1
    assert "gross_return" not in mixed


def test_matching_family_has_retrieval_priority(tmp_path):
    with EconomicMemoryStore(tmp_path / "memory.sqlite") as store:
        store.record(context(), {"net_return": -0.01}, {"family": "momentum"})
        store.record(context(), {"net_return": -0.02}, {"family": "defensive"})
        records = store.retrieve(context(), {"family": "momentum"}, limit=2)
        assert records[0]["strategy_family"] == "momentum"
        assert records[1]["strategy_family"] == "defensive"


def test_concurrent_connections_preserve_observations(tmp_path):
    path = tmp_path / "memory.sqlite"
    with EconomicMemoryStore(path):
        pass

    def write(index):
        with EconomicMemoryStore(path) as store:
            store.record(context(), {"net_return": -(index + 1) / 100}, {"name": f"candidate-{index}"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(12)))
    with EconomicMemoryStore(path) as store:
        assert len(store.list()) == 12


def test_store_ignores_unrelated_fields_and_redacts_obvious_tokens(tmp_path):
    with EconomicMemoryStore(tmp_path / "memory.sqlite") as store:
        records = store.record(context(), {"net_return": -0.1, "api_key": "private"},
                               {"name": "api_key=private", "credentials": "private"})
        serialized = str(records)
        assert "private" not in serialized
        assert "credentials" not in serialized


def test_execution_failure_requires_explicit_evidence(tmp_path):
    with EconomicMemoryStore(tmp_path / "memory.sqlite") as store:
        assert store.record(context(), {}, {}) == []
        records = store.record(context(), {"execution_success": False}, {})
        assert [record["category"] for record in records] == ["execution_failure"]
