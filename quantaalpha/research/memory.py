"""Context-isolated, evidence-based economic failure memory.

This is an additive observation store, not an alternative research/backtest
engine. It accepts only explicitly labelled validation observations. Missing
cost or subperiod measurements remain unknown rather than being manufactured.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any


class MemoryProtocolError(ValueError):
    """A memory operation would violate the declared research protocol."""


def _window(value: Any, label: str) -> list[str]:
    if isinstance(value, Mapping):
        value = [value.get("start"), value.get("end")]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise MemoryProtocolError(f"{label} must contain a start and end date.")
    try:
        start, end = [date.fromisoformat(str(item)[:10]) for item in value]
    except (TypeError, ValueError):
        raise MemoryProtocolError(f"{label} must contain ISO calendar dates.") from None
    if start > end:
        raise MemoryProtocolError(f"{label} start must not follow its end.")
    return [start.isoformat(), end.isoformat()]


def validate_context(context: Mapping[str, Any]) -> dict:
    if not isinstance(context, Mapping) or context.get("purpose") != "validation":
        raise MemoryProtocolError("Economic memory requires purpose='validation'; final-test observations are forbidden.")
    normalized = {"purpose": "validation"}
    for key in ("dataset_fingerprint", "execution_fingerprint"):
        value = context.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise MemoryProtocolError(f"{key} must be a nonempty fingerprint of at most 256 characters.")
        normalized[key] = value.strip()
    normalized["validation_window"] = _window(context.get("validation_window"), "validation_window")
    if context.get("holdout_window") is not None:
        holdout = _window(context["holdout_window"], "holdout_window")
        valid = normalized["validation_window"]
        if not (valid[1] < holdout[0] or holdout[1] < valid[0]):
            raise MemoryProtocolError("Validation and final holdout windows must not overlap.")
        normalized["holdout_window"] = holdout
    return normalized


def _context_key(context: dict) -> str:
    # Holdout metadata does not change which validation evidence is comparable.
    identity = {key: context[key] for key in (
        "dataset_fingerprint", "validation_window", "execution_fingerprint", "purpose"
    )}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def _first_numeric(values: Mapping, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _number(values.get(key))
        if value is not None:
            return value
    return None


def _redact(value: Any, limit: int = 1000) -> str:
    text = str(value)[:limit]
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[redacted]", text)
    return re.sub(
        r"(?i)\b(api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*[^\s,;]+",
        r"\1=[redacted]", text,
    )


def _safe_strategy(strategy: Mapping[str, Any] | None) -> dict:
    if not isinstance(strategy, Mapping):
        return {}
    result = {}
    for key in ("name", "family", "factor_name", "factor_expression", "lookback", "top_k", "topk", "n_drop", "num_leaves", "max_depth", "rebalance_days"):
        if key not in strategy:
            continue
        value = strategy[key]
        if isinstance(value, str):
            result[key] = _redact(value, 1500 if key == "factor_expression" else 160)
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and _number(value) is not None:
            result[key] = value
    if isinstance(strategy.get("factors"), list):
        result["factors"] = [_safe_strategy(item) for item in strategy["factors"][:20] if isinstance(item, Mapping)]
    return result


def normalize_result_metrics(result: Any) -> dict:
    """Extract observed metrics from an upstream Qlib result or a plain mapping.

    DataFrame/Series support uses their public methods without importing pandas,
    so inspecting stored memories does not require the ML runtime.
    """
    if result is None:
        return {}
    if not isinstance(result, Mapping):
        if hasattr(result, "columns") and hasattr(result, "iloc"):
            if len(result.columns) == 0:
                return {}
            result = result.iloc[:, 0].to_dict()
        elif hasattr(result, "to_dict"):
            result = result.to_dict()
    if not isinstance(result, Mapping):
        raise MemoryProtocolError("Metrics must be a mapping or a Qlib result table.")
    for key in ("source_split", "purpose", "split"):
        source = result.get(key)
        if isinstance(source, str) and source.lower() in {"test", "holdout", "final_test", "final_holdout"}:
            raise MemoryProtocolError("Final-test observations cannot enter economic memory.")
    if isinstance(result.get("metrics"), Mapping):
        result = result["metrics"]
        # Repeat the guard after unwrapping an engine result.
        for key in ("source_split", "purpose", "split"):
            source = result.get(key)
            if isinstance(source, str) and source.lower() in {"test", "holdout", "final_test", "final_holdout"}:
                raise MemoryProtocolError("Final-test observations cannot enter economic memory.")
    normalized = {}
    annual_net = _first_numeric(result, (
        "1day.excess_return_with_cost.annualized_return", "net_annualized_return", "annualized_return",
    ))
    annual_gross = _first_numeric(result, (
        "1day.excess_return_without_cost.annualized_return", "gross_annualized_return",
    ))
    total_net = _first_numeric(result, ("net_return", "net_total_return", "total_return"))
    total_gross = _first_numeric(result, ("gross_return", "gross_total_return"))
    # Prefer pairs with the same return basis; never compare annual and total returns.
    if annual_net is not None and annual_gross is not None:
        net, gross, basis = annual_net, annual_gross, "annualized"
    elif total_net is not None or total_gross is not None:
        net, gross, basis = total_net, total_gross, "total"
    else:
        net, gross, basis = annual_net, annual_gross, "annualized"
    if net is not None:
        normalized["net_return"] = net
    if gross is not None:
        normalized["gross_return"] = gross
    if net is not None or gross is not None:
        normalized["return_basis"] = basis
    for name, keys in (
        ("max_drawdown", ("1day.excess_return_with_cost.max_drawdown", "max_drawdown")),
        ("information_ratio", ("1day.excess_return_with_cost.information_ratio", "information_ratio")),
        ("ic", ("IC", "ic")),
        ("rank_ic", ("Rank IC", "RankIC", "rank_ic")),
        ("turnover", ("turnover",)),
    ):
        value = _first_numeric(result, keys)
        if value is not None:
            normalized[name] = value
    for key in ("subperiod_returns", "segment_returns"):
        if isinstance(result.get(key), (list, tuple)):
            observed = [_number(value) for value in result[key]]
            if len(observed) >= 2 and all(value is not None for value in observed):
                normalized["subperiod_returns"] = observed
                break
    if result.get("execution_success") is False or result.get("execution_failure") is True or result.get("execution_status") == "failed":
        normalized["execution_success"] = False
    return normalized


def _failures(metrics: dict) -> list[tuple[str, str, dict]]:
    failures = []
    net, gross = metrics.get("net_return"), metrics.get("gross_return")
    if net is not None and gross is not None:
        gap = gross - net
        if gap >= max(0.01, abs(gross) * 0.35) or (gross > 0 and net <= 0):
            failures.append(("cost_drag", "Observed execution costs materially reduced the gross result.", {
                "net_return": net, "gross_return": gross, "gross_net_gap": gap,
                "return_basis": metrics["return_basis"],
            }))
    if net is not None and net < 0:
        failures.append(("negative_net_return", "The observed validation return was negative after costs.", {
            "net_return": net, "return_basis": metrics["return_basis"],
        }))
    drawdown = metrics.get("max_drawdown")
    if drawdown is not None and abs(drawdown) >= 0.15:
        failures.append(("high_drawdown", "The observed validation drawdown exceeded the 15% research threshold.", {
            "max_drawdown": drawdown, "threshold": 0.15,
        }))
    if metrics.get("execution_success") is False:
        failures.append(("execution_failure", "The supplied execution result explicitly reported failure.", {
            "execution_success": False,
        }))
    subperiods = metrics.get("subperiod_returns")
    if subperiods and min(subperiods) < -0.02 and max(subperiods) > 0.02:
        failures.append(("regime_instability", "Observed chronological subperiod returns changed sign materially.", {
            "subperiod_returns": subperiods, "interpretation": "subperiod instability; causal market regimes are not inferred",
        }))
    return failures


class EconomicMemoryStore:
    """SQLite-backed store with transactional deduplication and contextual retrieval."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            self.path = str(Path(self.path).expanduser())
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout=30000")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS economic_memories (
                id TEXT PRIMARY KEY,
                context_key TEXT NOT NULL,
                category TEXT NOT NULL,
                strategy_family TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self._connection.execute("CREATE INDEX IF NOT EXISTS economic_context_idx ON economic_memories(context_key, created_at)")
        self._connection.commit()

    def record(self, context: dict, metrics: dict, strategy: dict, source: str = "validation") -> list[dict]:
        if source != "validation":
            raise MemoryProtocolError("Only validation observations may be recorded; holdout/test sources are forbidden.")
        context = validate_context(context)
        observed = normalize_result_metrics(metrics)
        safe_strategy = _safe_strategy(strategy)
        context_key = _context_key(context)
        records = []
        with self._lock, self._connection:
            for category, description, evidence in _failures(observed):
                evidence = {**evidence, "source_split": "validation"}
                identity = hashlib.sha256(json.dumps({
                    "context_key": context_key, "category": category,
                    "strategy": safe_strategy, "evidence": evidence,
                }, sort_keys=True, allow_nan=False).encode()).hexdigest()[:24]
                record = {
                    "id": identity, "category": category, "description": description,
                    "evidence": evidence, "metrics": observed, "strategy": safe_strategy,
                    "strategy_family": str(safe_strategy.get("family", "factor")),
                    "context": context, "dataset_fingerprint": context["dataset_fingerprint"],
                    "source": "validation", "source_split": "validation",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self._connection.execute(
                    "INSERT OR IGNORE INTO economic_memories VALUES (?, ?, ?, ?, ?, ?)",
                    (identity, context_key, category, record["strategy_family"],
                     json.dumps(record, sort_keys=True, allow_nan=False), record["created_at"]),
                )
                existing = self._connection.execute("SELECT payload FROM economic_memories WHERE id=?", (identity,)).fetchone()
                records.append(json.loads(existing["payload"]))
        return records

    def retrieve(self, context: dict, strategy: dict | None = None, limit: int = 5) -> list[dict]:
        context = validate_context(context)
        limit = self._limit(limit)
        family = _safe_strategy(strategy).get("family")
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM economic_memories WHERE context_key=? "
                "ORDER BY CASE WHEN strategy_family=? THEN 0 ELSE 1 END, created_at DESC, id DESC LIMIT ?",
                (_context_key(context), family or "", limit),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def list(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM economic_memories ORDER BY created_at DESC, id DESC LIMIT ?",
                (self._limit(limit),),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    @staticmethod
    def _limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Memory retrieval limit must be an integer from 1 to 1000.")
        return limit

    def close(self):
        with self._lock:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

