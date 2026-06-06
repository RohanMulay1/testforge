"""CLI: run the full optimize loop and emit a before/after report.

Examples:
    python scripts/run_optimize.py                         # defaults: 3 rounds, beam 2
    python scripts/run_optimize.py --rounds 4 --beam 3 --k-final 3
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

from testforge.optimizer import optimize
from testforge.reporting import (
    ensure_runs_dir,
    format_before_after,
    format_eval_table,
    save_json,
    save_text,
)


async def main() -> None:
    ap = argparse.ArgumentParser(description="Optimize the TestForge agent genome.")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--beam", type=int, default=2, help="candidate genomes proposed per round")
    ap.add_argument("--k-search", type=int, default=1, help="runs/task during search")
    ap.add_argument("--k-final", type=int, default=1, help="runs/task for the final before/after")
    ap.add_argument("--patience", type=int, default=2)
    ap.add_argument("--epsilon", type=float, default=0.5, help="min TRAIN gain to accept a candidate")
    ap.add_argument("--mutation-cap", type=int, default=30)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    result = await optimize(
        rounds=args.rounds, beam=args.beam, k_search=args.k_search, k_final=args.k_final,
        patience=args.patience, epsilon=args.epsilon, mutation_cap=args.mutation_cap,
        concurrency=args.concurrency, model=args.model, on_log=print,
    )

    report = "\n\n".join([
        format_before_after(result.baseline_test, result.best_test),
        "## Optimized genome (TRAIN headline)",
        f"- baseline TRAIN composite: **{result.baseline_train_score:.2f}**",
        f"- best TRAIN composite: **{result.best_train_score:.2f}** "
        f"(after {result.rounds_run} round(s))",
        "### Baseline (held-out)\n" + format_eval_table(result.baseline_test),
        "### Optimized (held-out)\n" + format_eval_table(result.best_test),
    ])

    runs = ensure_runs_dir()
    result.best_genome.save(runs / "best_genome.json")
    save_json(result.to_dict(), runs / "optimize_result.json")
    save_text(report, runs / "report.md")

    print("\n\n" + format_before_after(result.baseline_test, result.best_test))
    print(f"\nArtifacts written to {runs}/ (best_genome.json, optimize_result.json, report.md)")


if __name__ == "__main__":
    asyncio.run(main())
