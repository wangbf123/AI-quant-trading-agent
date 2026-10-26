"""Deterministic synthetic provider in Qlib's native binary format.

This fixture validates engineering, never market profitability. All factor
calculation, model fitting and execution use the retained upstream Qlib runner.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def fingerprint_provider(provider: str | Path) -> str:
    """Fingerprint actual calendar, instruments and price binaries, not a filename."""
    provider = Path(provider)
    digest = hashlib.sha256()
    files = sorted(path for path in provider.rglob("*") if path.is_file())
    for path in files:
        digest.update(path.relative_to(provider).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _build_demo_data(root: str | Path, seed: int = 42) -> dict:
    root = Path(root).resolve()
    provider = root / "qlib"
    provider.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-02", periods=540)
    calendar = days.strftime("%Y-%m-%d").tolist()
    (provider / "calendars").mkdir(exist_ok=True)
    (provider / "instruments").mkdir(exist_ok=True)
    (provider / "calendars" / "day.txt").write_text("\n".join(calendar) + "\n")
    symbols = [f"DEMO{i:03d}" for i in range(12)]
    market = rng.normal(0.0001, 0.007, len(days))
    returns = np.empty((len(days), len(symbols)))
    previous = np.zeros(len(symbols))
    for index in range(len(days)):
        persistence = 0.12 if index < 360 else -0.10
        returns[index] = market[index] + persistence * previous + rng.normal(0, 0.009, len(symbols))
        previous = returns[index]
    for index, symbol in enumerate([*symbols, "DEMO_BENCH"]):
        ret = returns[:, index] if index < len(symbols) else returns.mean(axis=1)
        close = (30 + index * 3) * np.cumprod(1 + ret)
        previous_close = np.r_[close[0], close[:-1]]
        opening = previous_close * (1 + rng.normal(0, 0.0015, len(days)))
        spread = rng.uniform(0.001, 0.012, len(days))
        volume = rng.integers(500_000, 3_000_000, len(days)).astype(float)
        fields = {
            "open": opening, "close": close,
            "high": np.maximum(opening, close) * (1 + spread),
            "low": np.minimum(opening, close) * (1 - spread),
            "volume": volume, "factor": np.ones(len(days)),
            "vwap": (opening + close) / 2,
            "change": np.r_[0, close[1:] / close[:-1] - 1],
        }
        folder = provider / "features" / symbol.lower()
        folder.mkdir(parents=True, exist_ok=True)
        for name, values in fields.items():
            binary = np.r_[0, values].astype("<f4").tobytes()
            (folder / f"{name}.day.bin").write_bytes(binary)
    instrument_text = "\n".join(f"{symbol}\t{calendar[0]}\t{calendar[-1]}" for symbol in symbols) + "\n"
    (provider / "instruments" / "demo.txt").write_text(instrument_text)
    (provider / "instruments" / "all.txt").write_text(instrument_text + f"DEMO_BENCH\t{calendar[0]}\t{calendar[-1]}\n")
    fingerprint = fingerprint_provider(provider)
    config_path = root / "backtest.yaml"
    config = {
        "random_seed": seed,
        "experiment": {"name": "synthetic_research", "recorder": "qlib", "output_dir": str(root / "results"), "output_metrics_file": "backtest_metrics.json"},
        "factor_source": {"type": "alpha158_20", "custom": {"json_files": []}},
        "data": {"provider_uri": str(provider), "region": "us", "market": "demo", "start_time": calendar[60], "end_time": calendar[443], "kernels": 1},
        "dataset": {
            "label": "Ref($close, -2) / Ref($close, -1) - 1",
            "learn_processors": [{"class": "ProcessInf"}, {"class": "Fillna", "kwargs": {"fields_group": "feature"}}, {"class": "DropnaLabel"}, {"class": "CSRankNorm", "kwargs": {"fields_group": "feature"}}],
            "infer_processors": [{"class": "ProcessInf"}, {"class": "Fillna", "kwargs": {"fields_group": "feature"}}, {"class": "CSRankNorm", "kwargs": {"fields_group": "feature"}}],
            "segments": {"train": [calendar[60], calendar[299]], "valid": [calendar[302], calendar[361]], "test": [calendar[364], calendar[443]]},
        },
        "model": {"type": "lgb", "params": {"loss": "mse", "learning_rate": 0.08, "num_leaves": 8, "max_depth": 3, "num_threads": 2, "seed": seed, "random_state": seed, "num_boost_round": 20, "early_stopping_round": 5, "min_child_samples": 20, "lambda_l1": 0.1, "lambda_l2": 1.0, "verbosity": -1}},
        "backtest": {
            "strategy": {"class": "TopkDropoutStrategy", "module_path": "qlib.contrib.strategy", "kwargs": {"signal": "<PRED>", "topk": 3, "n_drop": 1}},
            "backtest": {"start_time": calendar[364], "end_time": calendar[443], "account": 1_000_000, "benchmark": "DEMO_BENCH", "exchange_kwargs": {"deal_price": "open", "limit_threshold": None, "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 0, "trade_unit": 1, "volume_threshold": {"all": ["cum", "Ref($volume, 1) * 0.01"]}, "impact_cost": 0.001}},
        },
        "llm": {"enabled": False, "auto_extract_cache": False},
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    protocol = {
        "name": "Synthetic daily research · 12 assets",
        "dataset_fingerprint": fingerprint,
        "train": [calendar[60], calendar[299]], "tune": [calendar[302], calendar[361]],
        "validation": [calendar[364], calendar[443]], "holdout": [calendar[446], calendar[537]],
        "purge_sessions": 2, "calendar": calendar, "config_path": str(config_path), "data_root": str(root),
        "costs": config["backtest"]["backtest"]["exchange_kwargs"],
        "source": "synthetic", "seed": seed,
    }
    provenance = {"source": "synthetic", "generator": "aqr.synthetic.v1", "seed": seed, "assets": 12, "sessions": len(days), "dataset_fingerprint": fingerprint, "market_profitability_evidence": False}
    (root / "manifest.json").write_text(json.dumps(provenance, indent=2))
    return {"provider_uri": str(provider), "calendar": calendar, "dataset_fingerprint": fingerprint, "config_path": str(config_path), "protocol": protocol, "provenance": provenance}


def prepare_demo_data(root: str | Path, seed: int = 42) -> dict:
    """Reuse immutable fixture files and serialize concurrent initialization."""
    from filelock import FileLock
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    metadata = root / "fixture.json"
    with FileLock(str(root / ".prepare.lock"), timeout=30):
        if metadata.is_file():
            existing = json.loads(metadata.read_text())
            if existing["provenance"]["seed"] != seed:
                raise ValueError("Use another data directory for a different fixture seed")
            if fingerprint_provider(existing["provider_uri"]) != existing["dataset_fingerprint"]:
                raise ValueError("Existing demo provider changed; preserve its evidence and use another data directory")
            return existing
        generated = _build_demo_data(root, seed)
        metadata.write_text(json.dumps(generated, indent=2))
        return generated
