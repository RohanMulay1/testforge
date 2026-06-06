"""Unit tests for Markdown reporting + artifact writing (no SDK / API needed)."""

import json

from testforge.eval_harness import EvalResult
from testforge.genome import BASELINE
from testforge.metrics import TaskMeasurement
from testforge.reporting import (
    format_before_after,
    format_eval_table,
    save_json,
    save_text,
)


def _result(split, killed):
    ms = [
        TaskMeasurement(task="a", collected=True, passed=3, line_cov=1.0, branch_cov=1.0,
                        mutation_total=10, mutation_killed=killed, num_turns=4, cost_usd=0.01),
    ]
    return EvalResult(split=split, genome=BASELINE, measurements=ms, model="m")


def test_eval_table_contains_metrics_and_tasks():
    table = format_eval_table(_result("test", 8))
    assert "Composite" in table
    assert "Mutation score" in table
    assert "| a |" in table


def test_before_after_shows_deltas():
    baseline = _result("test", 4)
    best = _result("test", 9)
    report = format_before_after(baseline, best)
    assert "Before / After" in report
    assert "Δ" in report
    assert "+" in report  # mutation improved => positive delta


def test_save_json_and_text(tmp_path):
    jp = save_json({"hello": "world"}, tmp_path / "out" / "x.json")
    assert json.loads(jp.read_text(encoding="utf-8"))["hello"] == "world"
    tp = save_text("# report", tmp_path / "out" / "r.md")
    assert tp.read_text(encoding="utf-8") == "# report"
