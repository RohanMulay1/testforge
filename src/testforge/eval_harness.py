"""The Eval Harness: run a genome over a split and measure it objectively.

For each task: run the agent in a sandbox, then independently measure the produced
suite — collection validity, pass/fail, line + branch coverage, and mutation score.
The agent's self-reports are never trusted; every number here is recomputed by the
harness. Coverage + mutation are skipped (left at 0) when the suite is invalid or
red, because the composite gates those to 0 anyway — this also saves time.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .agent import resolve_model, write_tests
from .execution import run_coverage, run_pytest
from .genome import Genome
from .metrics import TaskMeasurement, aggregate
from .mutation import run_mutation_testing
from .sandbox import Sandbox, TaskSpec, load_tasks

ProgressFn = Callable[[TaskMeasurement], None]


@dataclass
class EvalResult:
    split: str
    genome: Genome
    measurements: list[TaskMeasurement] = field(default_factory=list)  # flat: n_tasks * k
    model: str = ""

    @property
    def aggregate(self) -> dict:
        return aggregate(self.measurements)

    def per_task(self) -> dict[str, float]:
        """Mean composite per task name (handles k>1 repeats)."""
        groups: dict[str, list[float]] = {}
        for m in self.measurements:
            groups.setdefault(m.task, []).append(m.composite)
        return {t: round(sum(v) / len(v), 2) for t, v in groups.items()}

    def to_dict(self) -> dict:
        return {
            "split": self.split,
            "model": self.model,
            "genome": self.genome.to_dict(),
            "aggregate": self.aggregate,
            "per_task": self.per_task(),
            "measurements": [m.to_dict() for m in self.measurements],
        }


async def evaluate_task(
    genome: Genome,
    task: TaskSpec,
    model: str | None = None,
    mutation_cap: int = 30,
    keep: bool = False,
) -> TaskMeasurement:
    """Run the agent on one task and return an independently-measured result."""
    with Sandbox(task, keep=keep) as sb:
        run = await write_tests(genome, sb, model=model)
        test_path = sb.find_test_file()

        if test_path is None:
            return TaskMeasurement(
                task=task.name, collected=False, num_turns=run.num_turns,
                cost_usd=run.cost_usd, error=run.error or "agent produced no test file",
            )

        pyrun = run_pytest(test_path, sb.dir)
        m = TaskMeasurement(
            task=task.name,
            collected=pyrun.collected,
            passed=pyrun.passed, failed=pyrun.failed,
            errors=pyrun.errors, skipped=pyrun.skipped,
            failures=[f"{f.nodeid}: {f.message}" for f in pyrun.failures][:8],
            num_turns=run.num_turns, cost_usd=run.cost_usd, error=run.error,
        )

        # Gate: only spend coverage/mutation budget on valid, green suites.
        if not m.all_passed:
            return m

        cov = run_coverage(sb.source_path, test_path, sb.dir)
        if cov.measured:
            m.line_cov = cov.line_pct
            m.branch_cov = cov.branch_pct
            m.uncovered_lines = cov.uncovered_lines
            m.partial_branches = cov.partial_branches

        mut = run_mutation_testing(sb.source_path, test_path, sb.dir, cap=mutation_cap)
        if mut.error is None:
            m.mutation_total = mut.total
            m.mutation_killed = mut.killed
            m.surviving_mutants = mut.surviving[:12]
        return m


async def evaluate_split(
    genome: Genome,
    split: str,
    model: str | None = None,
    k: int = 1,
    mutation_cap: int = 30,
    concurrency: int = 1,
    on_progress: ProgressFn | None = None,
) -> EvalResult:
    """Evaluate a genome over every task in a split, ``k`` times each."""
    tasks = load_tasks(split)
    model = resolve_model(model)
    jobs = [(task, rep) for task in tasks for rep in range(k)]

    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: list[TaskMeasurement] = []

    async def _run(task: TaskSpec) -> TaskMeasurement:
        async with semaphore:
            m = await evaluate_task(genome, task, model=model, mutation_cap=mutation_cap)
            if on_progress:
                on_progress(m)
            return m

    if concurrency <= 1:
        for task, _rep in jobs:
            results.append(await _run(task))
    else:
        results = list(await asyncio.gather(*[_run(task) for task, _rep in jobs]))

    return EvalResult(split=split, genome=genome, measurements=results, model=model)


async def evaluate_single_file(
    genome: Genome,
    source_file: str | Path,
    model: str | None = None,
    mutation_cap: int = 30,
    keep: bool = False,
) -> TaskMeasurement:
    """Run the agent against an arbitrary .py file (the 'point it at any file' demo)."""
    path = Path(source_file).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    spec = TaskSpec(name=path.stem, source_path=path, source_filename=path.name)
    return await evaluate_task(genome, spec, model=model, mutation_cap=mutation_cap, keep=keep)
