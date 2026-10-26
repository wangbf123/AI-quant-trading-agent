"""Pure configuration guards around the existing QuantaAlpha/Qlib runner.

The finalization permission and one-shot state belong to the experiment store.
This module never runs a model or substitutes a home-grown backtest engine.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any


WINDOWS = ("train", "tune", "validation", "holdout")
LABEL_HORIZON_SESSIONS = 2


def _date(value: Any, field: str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} is not a valid date") from error


def _calendar(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("calendar must contain the actual trading sessions")
    sessions = [_date(value, "calendar session") for value in values]
    if sessions != sorted(set(sessions)):
        raise ValueError("calendar sessions must be strictly increasing and unique")
    return sessions


def _check_gaps(windows: list[tuple[str, list[str]]], sessions: list[str], purge: int) -> dict:
    gaps = {}
    for name, (start, end) in windows:
        if bisect_left(sessions, start) == bisect_right(sessions, end):
            raise ValueError(f"{name} has no trading sessions in the supplied calendar")
    for (previous, (_, end)), (following, (start, _)) in zip(windows, windows[1:]):
        count = bisect_left(sessions, start) - bisect_right(sessions, end)
        if count < purge:
            raise ValueError(
                f"{previous} → {following} needs at least {purge} excluded trading "
                f"sessions for label purge; found {count}"
            )
        gaps[f"{previous}_to_{following}"] = count
    return gaps


def validate_protocol(protocol: dict, calendar: list[str] | None = None) -> dict:
    """Normalize four disjoint windows, optionally verifying real-session purge.

    Without a provider trading calendar this validates date ordering only and
    returns ``calendar_verified=False``. Callers must not represent that as a
    verified trading-session gap. Unknown application fields are preserved.
    """
    if not isinstance(protocol, dict):
        raise ValueError("protocol must be an object")
    normalized = deepcopy(protocol)
    for field in ("name", "dataset_fingerprint"):
        value = normalized.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"protocol.{field} is required")
        normalized[field] = value.strip()
    purge = normalized.get("purge_sessions", LABEL_HORIZON_SESSIONS)
    if isinstance(purge, bool) or not isinstance(purge, int) or purge < LABEL_HORIZON_SESSIONS:
        raise ValueError("purge_sessions must be an integer >= 2 for the forward-return label")
    normalized["purge_sessions"] = purge
    for field in WINDOWS:
        bounds = normalized.get(field)
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            raise ValueError(f"protocol.{field} must be [start, end]")
        bounds = [_date(value, f"{field} bound") for value in bounds]
        if bounds[0] > bounds[1]:
            raise ValueError(f"{field} start must not follow its end")
        normalized[field] = bounds
    for previous, following in zip(WINDOWS, WINDOWS[1:]):
        if normalized[previous][1] >= normalized[following][0]:
            raise ValueError(f"{previous} and {following} overlap or are out of order")

    supplied_calendar = calendar if calendar is not None else normalized.get("calendar")
    normalized["calendar_verified"] = False
    normalized["purge_gaps"] = {}
    if supplied_calendar is not None:
        sessions = _calendar(supplied_calendar)
        normalized["purge_gaps"] = _check_gaps(
            [(name, normalized[name]) for name in WINDOWS], sessions, purge,
        )
        normalized["calendar"] = sessions
        normalized["calendar_verified"] = True

    for key in ("costs", "strategy"):
        if key in normalized and not isinstance(normalized[key], dict):
            raise ValueError(f"protocol.{key} must be an object")
    for key, value in normalized.get("costs", {}).items():
        if key in ("open_cost", "close_cost", "min_cost", "impact_cost"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"costs.{key} must be finite and nonnegative")
    for key in ("topk", "n_drop"):
        if key in normalized.get("strategy", {}):
            value = normalized["strategy"][key]
            minimum = 1 if key == "topk" else 0
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"strategy.{key} must be an integer >= {minimum}")
    return normalized


def evaluation_config(base_config: dict, protocol: dict, purpose: str) -> dict:
    """Build an isolated upstream ``BacktestRunner`` configuration.

    ``research`` evaluates only the research validation window. ``finalize``
    evaluates the final holdout; callers must first atomically lock the selected
    candidate in their experiment store. Neither call grants that permission.
    """
    if purpose in ("research", "validation"):
        selected = "validation"
        purpose = "research"
    elif purpose in ("finalize", "holdout", "test"):
        selected = "holdout"
        purpose = "finalize"
    else:
        raise ValueError("purpose must be research or finalize")
    normalized = validate_protocol(protocol)
    if not isinstance(base_config, dict):
        raise ValueError("base_config must be an object")
    config = deepcopy(base_config)
    for field in ("data", "dataset", "backtest"):
        if not isinstance(config.get(field), dict):
            raise ValueError(f"base_config.{field} is required")
    # The base label is trusted Qlib syntax, but its forward horizon must fit
    # the declared purge gap; longer labels cannot silently reuse two sessions.
    future_offsets = [int(value) for value in re.findall(r"Ref\s*\([^,]+,\s*-(\d+)\s*\)", str(config["dataset"].get("label", "")))]
    if future_offsets and max(future_offsets) > normalized["purge_sessions"]:
        raise ValueError("Label forward horizon exceeds the declared purge_sessions")
    config["dataset"]["segments"] = {
        "train": list(normalized["train"]),
        "valid": list(normalized["tune"]),
        "test": list(normalized[selected]),
    }
    config["data"]["start_time"] = normalized["train"][0]
    config["data"]["end_time"] = normalized[selected][1]
    backtest = config["backtest"].setdefault("backtest", {})
    backtest["start_time"], backtest["end_time"] = normalized[selected]
    exchange = backtest.setdefault("exchange_kwargs", {})
    exchange.update(deepcopy(normalized.get("costs", {})))
    for field in ("open_cost", "close_cost", "min_cost"):
        if field not in exchange:
            raise ValueError(f"a fixed {field} is required for cost-aware evaluation")
        value = exchange[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"exchange_kwargs.{field} must be finite and nonnegative")
    strategy = config["backtest"].setdefault("strategy", {})
    strategy.setdefault("kwargs", {}).update(deepcopy(normalized.get("strategy", {})))
    identity = {key: normalized[key] for key in (
        "name", "dataset_fingerprint", *WINDOWS, "purge_sessions",
    )}
    identity.update(costs=exchange, strategy=strategy)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
    # Only execution windows are copied into the config. A research worker must
    # not receive the final holdout range or its calendar/data through metadata.
    config["research_protocol"] = {
        "name": normalized["name"],
        "dataset_fingerprint": normalized["dataset_fingerprint"],
        "purpose": purpose,
        "protocol_hash": digest,
        "purge_sessions": normalized["purge_sessions"],
        "calendar_verified": normalized["calendar_verified"],
        "evaluation_window": list(normalized[selected]),
        "require_calendar_verification": True,
    }
    return config


def validate_execution_calendar(config: dict, calendar: list[str]) -> None:
    """Recheck the three exposed Qlib segments against the provider calendar."""
    policy = config.get("research_protocol")
    if not policy:
        return
    segments = config["dataset"]["segments"]
    windows = [(name, [_date(value, name) for value in segments[name]])
               for name in ("train", "valid", "test")]
    _check_gaps(windows, _calendar(calendar), policy["purge_sessions"])
    selected = windows[-1][1]
    bt = config["backtest"]["backtest"]
    if [_date(bt["start_time"], "backtest start"), _date(bt["end_time"], "backtest end")] != selected:
        raise ValueError("backtest window differs from the protocol evaluation window")
    if _date(config["data"]["end_time"], "data end") > selected[1]:
        raise ValueError("data end exceeds the selected evaluation window")
