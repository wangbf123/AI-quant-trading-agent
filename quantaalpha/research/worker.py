"""Isolated process for the retained upstream BacktestRunner (no new engine)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    # Bind the provider to this run, rather than any unrelated shell setting.
    os.environ["QLIB_DATA_DIR"] = config["data"]["provider_uri"]
    os.environ["OMP_NUM_THREADS"] = str(config["data"].get("kernels", 1))
    os.environ["MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING"] = "false"
    from quantaalpha.backtest.runner import BacktestRunner

    class CandidateRunner(BacktestRunner):
        def _load_factors(self):
            expressions, custom = super()._load_factors()
            selected = self.config.get("research_candidate", {}).get("feature_names")
            if selected:
                if not set(selected).issubset(expressions):
                    raise ValueError("Candidate requests an unknown upstream factor")
                expressions = {name: expressions[name] for name in selected}
            return expressions, custom

    runner = CandidateRunner(args.config)
    metrics = runner.run(factor_source="alpha158_20", output_name="candidate")
    Path(args.output).write_text(json.dumps(metrics, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
