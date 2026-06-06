"""Unit tests for composite scoring + aggregation (pure)."""

from testforge.metrics import (
    W_BRANCH,
    W_LINE,
    W_MUTATION,
    W_PASS,
    TaskMeasurement,
    aggregate,
)


def _perfect(task="t") -> TaskMeasurement:
    return TaskMeasurement(
        task=task, collected=True, passed=5, failed=0, errors=0,
        line_cov=1.0, branch_cov=1.0, mutation_total=10, mutation_killed=10,
    )


def test_perfect_suite_scores_100():
    assert _perfect().composite == 100.0


def test_weights_sum_to_one():
    assert abs((W_MUTATION + W_BRANCH + W_LINE + W_PASS) - 1.0) < 1e-9


def test_failing_suite_is_gated_to_zero():
    m = _perfect()
    m.failed = 1  # one failing test trips the gate
    assert m.composite == 0.0


def test_non_collecting_suite_is_gated_to_zero():
    m = _perfect()
    m.collected = False
    assert m.composite == 0.0


def test_empty_suite_scores_zero():
    # Collects but contains no tests => not all_passed => gated.
    m = TaskMeasurement(task="t", collected=True, passed=0)
    assert m.composite == 0.0


def test_mutation_dominates_quality_term():
    # Same coverage, different mutation score => higher composite for more kills.
    low = TaskMeasurement(task="t", collected=True, passed=3, line_cov=1.0,
                          branch_cov=1.0, mutation_total=10, mutation_killed=2)
    high = TaskMeasurement(task="t", collected=True, passed=3, line_cov=1.0,
                           branch_cov=1.0, mutation_total=10, mutation_killed=9)
    assert high.composite > low.composite


def test_mutation_score_handles_zero_total():
    m = TaskMeasurement(task="t", collected=True, passed=1, mutation_total=0)
    assert m.mutation_score == 0.0


def test_partial_coverage_composite_math():
    m = TaskMeasurement(task="t", collected=True, passed=2, line_cov=0.5,
                        branch_cov=0.5, mutation_total=4, mutation_killed=2)
    # gate=1; quality = .40*.5 + .30*.5 + .20*.5 + .10*1.0 = .2+.15+.1+.1 = .55?
    # .40*.5=.20, .30*.5=.15, .20*.5=.10, .10*1=.10 => .55 -> hmm recompute:
    expected = 100.0 * (0.40 * 0.5 + 0.30 * 0.5 + 0.20 * 0.5 + 0.10 * 1.0)
    assert m.composite == round(expected, 2)


def test_aggregate_means():
    ms = [_perfect("a"), TaskMeasurement(task="b", collected=False)]
    agg = aggregate(ms)
    assert agg["n"] == 2
    assert agg["composite"] == 50.0      # (100 + 0) / 2
    assert agg["valid_rate"] == 0.5
    assert agg["pass_rate"] == 0.5


def test_aggregate_empty():
    agg = aggregate([])
    assert agg["n"] == 0
    assert agg["composite"] == 0.0


def test_to_dict_includes_derived_fields():
    d = _perfect().to_dict()
    assert d["composite"] == 100.0
    assert d["mutation_score"] == 1.0
    assert d["num_tests"] == 5
