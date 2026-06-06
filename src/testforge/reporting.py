"""Human-readable reporting: eval tables and before/after comparisons.

Renders Markdown so output drops straight into the README / a PR, and writes JSON
sidecars for programmatic use. Kept dependency-free (no pandas/tabulate).
"""

from __future__ import annotations

import json
from pathlib import Path

from .eval_harness import EvalResult
from .paths import RUNS_DIR

_METRIC_ROWS = [
    ("Composite (0-100)", "composite"),
    ("Mutation score", "mutation_score"),
    ("Branch coverage", "branch_cov"),
    ("Line coverage", "line_cov"),
    ("Pass rate", "pass_rate"),
    ("Valid rate", "valid_rate"),
    ("Avg turns", "avg_turns"),
    ("Total cost (USD)", "total_cost_usd"),
]


def format_eval_table(result: EvalResult) -> str:
    agg = result.aggregate
    lines = [
        f"### Eval — split=`{result.split}`  model=`{result.model}`  n={agg['n']}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for label, key in _METRIC_ROWS:
        lines.append(f"| {label} | {_fmt(agg.get(key, 0.0), key)} |")
    lines += ["", "| Task | Composite |", "| --- | ---: |"]
    for task, score in result.per_task().items():
        lines.append(f"| {task} | {score:.2f} |")
    return "\n".join(lines)


def format_before_after(baseline: EvalResult, best: EvalResult) -> str:
    a, b = baseline.aggregate, best.aggregate
    lines = [
        f"## Before / After — held-out split=`{baseline.split}`",
        "",
        "| Metric | Baseline | Optimized | Δ |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key in _METRIC_ROWS:
        av, bv = a.get(key, 0.0), b.get(key, 0.0)
        delta = bv - av
        sign = "+" if delta >= 0 else ""
        lines.append(f"| {label} | {_fmt(av, key)} | {_fmt(bv, key)} | {sign}{_fmt(delta, key)} |")

    lines += ["", "### Per-task composite", "", "| Task | Baseline | Optimized | Δ |",
              "| --- | ---: | ---: | ---: |"]
    base_tasks, best_tasks = baseline.per_task(), best.per_task()
    for task in base_tasks:
        av, bv = base_tasks.get(task, 0.0), best_tasks.get(task, 0.0)
        delta = bv - av
        sign = "+" if delta >= 0 else ""
        lines.append(f"| {task} | {av:.2f} | {bv:.2f} | {sign}{delta:.2f} |")
    return "\n".join(lines)


def _fmt(value: float, key: str) -> str:
    if key in ("composite", "avg_turns"):
        return f"{value:.2f}"
    if key == "total_cost_usd":
        return f"{value:.4f}"
    return f"{value:.3f}"


def ensure_runs_dir(subdir: str = "") -> Path:
    target = RUNS_DIR / subdir if subdir else RUNS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_json(obj: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return path


def save_text(text: str, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
