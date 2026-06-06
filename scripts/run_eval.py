"""CLI: evaluate a genome over a split and print/save the metrics table.

Examples:
    python scripts/run_eval.py --genome baseline --split test
    python scripts/run_eval.py --genome runs/best_genome.json --split test --k 3
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
from testforge.reporting import ensure_runs_dir, format_eval_table, save_json


def _load_genome(spec: str) -> Genome:
    return BASELINE if spec == "baseline" else Genome.load(spec)


def _progress(m: TaskMeasurement) -> None:
    status = "ok " if m.all_passed else "RED"
    print(f"  [{status}] {m.task:16} composite={m.composite:6.2f}  "
          f"cov(l/b)={m.line_cov:.2f}/{m.branch_cov:.2f}  "
          f"mut={m.mutation_killed}/{m.mutation_total}  turns={m.num_turns}"
          + (f"  err={m.error}" if m.error else ""))


async def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate a genome on a split.")
    ap.add_argument("--genome", default="baseline", help="'baseline' or path to a genome JSON")
    ap.add_argument("--split", default="test", choices=["train", "test", "all"])
    ap.add_argument("--k", type=int, default=1, help="runs per task (averaged)")
    ap.add_argument("--mutation-cap", type=int, default=30)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default=None, help="path to write metrics JSON")
    args = ap.parse_args()

    genome = _load_genome(args.genome)
    print(f"== Evaluating genome={args.genome} on split={args.split} (k={args.k}) ==\n")

    result = await evaluate_split(
        genome, args.split, model=args.model, k=args.k,
        mutation_cap=args.mutation_cap, concurrency=args.concurrency,
        on_progress=_progress,
    )

    print("\n" + format_eval_table(result))

    out = Path(args.out) if args.out else ensure_runs_dir() / f"eval_{args.split}_{args.genome.replace('/', '_').replace('.json','')}.json"
    save_json(result.to_dict(), out)
    print(f"\nSaved metrics to {out}")


if __name__ == "__main__":
    asyncio.run(main())
