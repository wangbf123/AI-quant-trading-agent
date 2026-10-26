import copy
import json
from pathlib import Path

import pytest

from quantaalpha.research.fixture import fingerprint_provider, prepare_demo_data
from quantaalpha.research.protocol import evaluation_config, validate_execution_calendar, validate_protocol


@pytest.fixture
def fixture(tmp_path):
    return prepare_demo_data(tmp_path / "fixture")


def test_four_windows_and_real_session_label_purge(fixture):
    protocol = validate_protocol(fixture["protocol"])
    assert protocol["calendar_verified"]
    assert set(protocol["purge_gaps"].values()) == {2}
    broken = copy.deepcopy(protocol)
    broken["tune"][0] = broken["train"][1]
    with pytest.raises(ValueError, match="overlap"):
        validate_protocol(broken)
    broken = copy.deepcopy(protocol)
    broken["tune"][0] = protocol["calendar"][301]
    with pytest.raises(ValueError, match="purge"):
        validate_protocol(broken)


def test_research_excludes_holdout_and_does_not_mutate_base(fixture):
    base = json.loads(Path(fixture["config_path"]).read_text())
    original = copy.deepcopy(base)
    protocol = fixture["protocol"]
    research = evaluation_config(base, protocol, "research")
    final = evaluation_config(base, protocol, "finalize")
    assert base == original
    assert research["dataset"]["segments"]["test"] == protocol["validation"]
    assert research["data"]["end_time"] < protocol["holdout"][0]
    assert protocol["holdout"][0] not in json.dumps(research)
    assert final["dataset"]["segments"]["test"] == protocol["holdout"]
    validate_execution_calendar(research, fixture["calendar"])
    research["backtest"]["backtest"]["end_time"] = protocol["holdout"][1]
    with pytest.raises(ValueError, match="differs"):
        validate_execution_calendar(research, fixture["calendar"])


def test_fingerprint_covers_actual_price_bytes_and_is_reproducible(fixture, tmp_path):
    second = prepare_demo_data(tmp_path / "second")
    assert second["dataset_fingerprint"] == fixture["dataset_fingerprint"]
    provider = Path(fixture["provider_uri"])
    path = next(provider.rglob("close.day.bin"))
    binary = bytearray(path.read_bytes())
    binary[-1] ^= 1
    path.write_bytes(binary)
    assert fingerprint_provider(provider) != fixture["dataset_fingerprint"]


def test_protocol_requires_explicit_costs_and_minimum_label_gap(fixture):
    protocol = copy.deepcopy(fixture["protocol"])
    protocol["purge_sessions"] = 1
    with pytest.raises(ValueError, match=">= 2"):
        validate_protocol(protocol)
    protocol = copy.deepcopy(fixture["protocol"])
    protocol["costs"]["open_cost"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        validate_protocol(protocol)
