"""CLI: run the test-writing agent on a single file or task and show everything.

Examples:
    python scripts/run_agent.py stack                       # a bundled task by name
    python scripts/run_agent.py path/to/mymodule.py         # any local .py file
    python scripts/run_agent.py stack --genome runs/best_genome.json --keep
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

from testforge.agent import resolve_model, write_tests
from testforge.execution import run_coverage, run_pytest
from testforge.genome import BASELINE, Genome
from testforge.metrics import TaskMeasurement
from testforge.mutation import run_mutation_testing
from testforge.paths import TASKS_DIR
from testforge.sandbox import Sandbox, TaskSpec, load_manifest


def _resolve_spec(target: str) -> TaskSpec:
    manifest = load_manifest()
    source_filename = manifest.get("source_filename", "source.py")
    # Bundled task name?
    task_dir = TASKS_DIR / target / source_filename
    if task_dir.exists():
        return TaskSpec(name=target, source_path=task_dir, source_filename=source_filename)
    # Arbitrary file path?
    path = Path(target).resolve()
    if path.exists() and path.suffix == ".py":
        return TaskSpec(name=path.stem, source_path=path, source_filename=path.name)
    raise SystemExit(f"'{target}' is neither a bundled task nor an existing .py file")


def _load_genome(spec: str) -> Genome:
    return BASELINE if spec == "baseline" else Genome.load(spec)


async def main() -> None:
    ap = argparse.ArgumentParser(description="Run the TestForge agent on one file/task.")
    ap.add_argument("target", help="A bundled task name (e.g. 'stack') or a path to a .py file")
    ap.add_argument("--genome", default="baseline", help="'baseline' or path to a genome JSON")
    ap.add_argument("--model", default=None)
    ap.add_argument("--mutation-cap", type=int, default=30)
    ap.add_argument("--keep", action="store_true", help="keep the sandbox dir for inspection")
    args = ap.parse_args()

    spec = _resolve_spec(args.target)
    genome = _load_genome(args.genome)
    model = resolve_model(args.model)
    print(f"== Agent run ==  task={spec.name}  genome={args.genome}  model={model}\n")

    with Sandbox(spec, keep=args.keep) as sb:
        run = await write_tests(genome, sb, model=model)
        print(f"-- result: {run.subtype}  turns={run.num_turns}  "
              f"tool_calls={run.tool_calls}  cost=${run.cost_usd:.4f}")
        if run.error:
            print(f"-- agent error: {run.error}")

        test_path = sb.find_test_file()
        if test_path is None:
            print("\n!! No test file produced.")
            return

        print(f"\n-- generated {test_path.name} --\n")
        print(test_path.read_text(encoding="utf-8"))

        pyrun = run_pytest(test_path, sb.dir)
        m = TaskMeasurement(
            task=spec.name, collected=pyrun.collected, passed=pyrun.passed,
            failed=pyrun.failed, errors=pyrun.errors, skipped=pyrun.skipped,
            num_turns=run.num_turns, cost_usd=run.cost_usd,
        )
        if m.all_passed:
            cov = run_coverage(sb.source_path, test_path, sb.dir)
            if cov.measured:
                m.line_cov, m.branch_cov = cov.line_pct, cov.branch_pct
            mut = run_mutation_testing(sb.source_path, test_path, sb.dir, cap=args.mutation_cap)
            if mut.error is None:
                m.mutation_total, m.mutation_killed = mut.total, mut.killed

        print("\n-- measurement --")
        print(f"  collected={m.collected}  passed={m.passed} failed={m.failed} errors={m.errors}")
        print(f"  line_cov={m.line_cov:.3f}  branch_cov={m.branch_cov:.3f}  "
              f"mutation={m.mutation_killed}/{m.mutation_total} ({m.mutation_score:.3f})")
        print(f"  COMPOSITE={m.composite:.2f} / 100")
        if args.keep:
            print(f"\n  sandbox kept at: {sb.dir}")


if __name__ == "__main__":
    asyncio.run(main())
