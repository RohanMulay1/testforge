"""CLI: compare two genomes on a split and emit a before/after report.

Useful for a clean, variance-reduced held-out comparison (higher --k) without
re-running the whole optimize loop.

Example:
    python scripts/run_compare.py --best runs/best_genome.json --split test --k 3
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from testforge.eval_harness import evaluate_split
from testforge.genome import BASELINE, Genome
from testforge.metrics import TaskMeasurement
from testforge.reporting import ensure_runs_dir, format_before_after, save_text


def _progress(tag):
    def fn(m: TaskMeasurement) -> None:
        status = "ok " if m.all_passed else "RED"
        print(f"  [{tag}][{status}] {m.task:16} composite={m.composite:6.2f}  "
              f"mut={m.mutation_killed}/{m.mutation_total}")
    return fn


async def main() -> None:
    ap = argparse.ArgumentParser(description="Compare baseline vs a genome on a split.")
    ap.add_argument("--best", required=True, help="path to the optimized genome JSON")
    ap.add_argument("--split", default="test", choices=["train", "test", "all"])
    ap.add_argument("--k", type=int, default=3, help="runs/task (averaged) to reduce variance")
    ap.add_argument("--mutation-cap", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    best = Genome.load(args.best)
    print(f"== Comparing baseline vs {args.best} on split={args.split} (k={args.k}) ==\n")

    print("-- baseline --")
    baseline_eval = await evaluate_split(
        BASELINE, args.split, model=args.model, k=args.k,
        mutation_cap=args.mutation_cap, concurrency=args.concurrency,
        on_progress=_progress("base"),
    )
    print("-- optimized --")
    best_eval = await evaluate_split(
        best, args.split, model=args.model, k=args.k,
        mutation_cap=args.mutation_cap, concurrency=args.concurrency,
        on_progress=_progress("best"),
    )

    report = format_before_after(baseline_eval, best_eval)
    print("\n" + report)
    out = ensure_runs_dir() / f"compare_{args.split}_k{args.k}.md"
    save_text(report, out)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
