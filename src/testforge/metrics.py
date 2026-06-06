"""Scoring: turn raw measurements into a composite quality score.

The composite deliberately weights **mutation score** highest — it is the metric
that distinguishes tests that assert behavior from tests that merely execute lines.
A suite that does not collect or does not fully pass scores 0 (the validity gate),
because an invalid/red suite has no measurable quality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Composite weights (sum to 1.0 within the gated quality term).
W_MUTATION = 0.40
W_BRANCH = 0.30
W_LINE = 0.20
W_PASS = 0.10


@dataclass
class TaskMeasurement:
    """Everything the harness measured for one (task, run), computed independently
    of anything the agent claimed."""

    task: str
    collected: bool = False
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    line_cov: float = 0.0
    branch_cov: float = 0.0
    mutation_total: int = 0
    mutation_killed: int = 0
    surviving_mutants: list[str] = field(default_factory=list)
    uncovered_lines: list[int] = field(default_factory=list)
    partial_branches: list[int] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    num_turns: int = 0
    cost_usd: float = 0.0
    error: str | None = None

    @property
    def num_tests(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def all_passed(self) -> bool:
        return self.collected and self.failed == 0 and self.errors == 0 and self.passed > 0

    @property
    def pass_validity(self) -> float:
        return 1.0 if self.all_passed else 0.0

    @property
    def mutation_score(self) -> float:
        return (self.mutation_killed / self.mutation_total) if self.mutation_total else 0.0

    @property
    def composite(self) -> float:
        """0..100. Gated to 0 unless the suite collects AND fully passes."""
        gate = 1.0 if (self.collected and self.all_passed) else 0.0
        quality = (
            W_MUTATION * self.mutation_score
            + W_BRANCH * self.branch_cov
            + W_LINE * self.line_cov
            + W_PASS * self.pass_validity
        )
        return round(100.0 * gate * quality, 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["num_tests"] = self.num_tests
        d["mutation_score"] = round(self.mutation_score, 4)
        d["composite"] = self.composite
        return d


def aggregate(measurements: list[TaskMeasurement]) -> dict:
    """Mean composite + per-metric means across a split."""
    if not measurements:
        return {
            "n": 0, "composite": 0.0, "line_cov": 0.0, "branch_cov": 0.0,
            "mutation_score": 0.0, "pass_rate": 0.0, "valid_rate": 0.0,
            "avg_turns": 0.0, "total_cost_usd": 0.0,
        }
    n = len(measurements)
    return {
        "n": n,
        "composite": round(_mean(m.composite for m in measurements), 2),
        "line_cov": round(_mean(m.line_cov for m in measurements), 4),
        "branch_cov": round(_mean(m.branch_cov for m in measurements), 4),
        "mutation_score": round(_mean(m.mutation_score for m in measurements), 4),
        "pass_rate": round(_mean(m.pass_validity for m in measurements), 4),
        "valid_rate": round(_mean(1.0 if m.collected else 0.0 for m in measurements), 4),
        "avg_turns": round(_mean(m.num_turns for m in measurements), 2),
        "total_cost_usd": round(sum(m.cost_usd for m in measurements), 4),
    }


def _mean(values) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0
