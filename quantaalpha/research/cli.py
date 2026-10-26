"""Developer CLI using the same persistent protocol lifecycle as the API."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .experiment import create_demo_protocol, finalize_research, run_research
from .fixture import fingerprint_provider
from .store import ResearchStore


def main():
    parser = argparse.ArgumentParser(description="Agentic Quant Research Platform · QuantaAlpha extension")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Real Qlib research on explicitly synthetic data")
    demo.add_argument("--budget", type=int, default=2)
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--ablation", action="store_true")
    demo.add_argument("--finalize", action="store_true", help="Freeze selected candidate and evaluate final holdout once")
    demo.add_argument("--planner", choices=["demo", "llm"], default="demo")
    demo.add_argument("--data-dir", default=os.getenv("AQR_DATA_DIR", "data/results/research-cli"))
    prepare = sub.add_parser("prepare-demo", help="Prepare an immutable Qlib fixture and print protocol JSON")
    prepare.add_argument("--data-dir", default="data/results/demo")
    fingerprint = sub.add_parser("fingerprint", help="Fingerprint an existing Qlib local provider")
    fingerprint.add_argument("provider")
    args = parser.parse_args()
    if args.command == "fingerprint":
        print(fingerprint_provider(Path(args.provider).expanduser()))
        return
    if args.command == "prepare-demo":
        print(json.dumps(create_demo_protocol(args.data_dir), ensure_ascii=False, indent=2))
        return
    store = ResearchStore(args.data_dir, os.getenv("AQR_DATABASE_URL"))
    protocol = create_demo_protocol(store.data_root / "demo")
    entry = store.create_protocol(protocol)
    config = {"budget": args.budget, "seed": args.seed, "use_memory": True, "run_ablation": args.ablation, "planner": args.planner}
    task = store.start_task(entry["id"], config)
    config["output_dir"] = task["run_dir"]
    try:
        result = run_research(entry["protocol"], config, lambda event: print(event["message"], flush=True))
        store.finish_task(task["id"], result=result)
    except Exception as error:
        store.finish_task(task["id"], error=f"{type(error).__name__}: {error}")
        raise
    if args.finalize:
        entry = store.freeze(entry["id"], result["best_candidate"]["id"])
        task = store.start_task(entry["id"], config, "finalize")
        config["output_dir"] = task["run_dir"]
        try:
            result = finalize_research(entry["protocol"], entry["result"], config)
            store.finish_task(task["id"], result=result)
        except Exception as error:
            store.finish_task(task["id"], error=f"{type(error).__name__}: {error}")
            raise
    exported = store.get_protocol(entry["id"])
    output = store.data_root / f"research-{entry['id']}.json"
    output.write_text(json.dumps(exported, ensure_ascii=False, indent=2, allow_nan=False))
    print(json.dumps({"protocol_id": entry["id"], "state": exported["state"], "validation_metrics": result["validation"]["metrics"], "holdout_metrics": (result.get("holdout") or {}).get("metrics"), "evidence": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
