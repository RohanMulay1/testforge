"""Tests for the execution layer (run pytest + coverage via subprocess).

These shell out to pytest/coverage but use tiny inline fixtures, so they stay fast.
The coverage test guards a real regression: a ``*source.py`` include glob matched
unrelated site-packages files named source.py, so the parser must pin the exact file.
"""

from pathlib import Path

from testforge.execution import run_coverage, run_pytest

SRC = "def classify(n):\n    if n < 0:\n        return 'neg'\n    if n == 0:\n        return 'zero'\n    return 'pos'\n"


def _write(tmp_path: Path, test_body: str) -> tuple[Path, Path]:
    source = tmp_path / "source.py"
    source.write_text(SRC, encoding="utf-8")
    test = tmp_path / "test_source.py"
    test.write_text(test_body, encoding="utf-8")
    return source, test


def test_run_pytest_reports_pass(tmp_path: Path):
    _, test = _write(
        tmp_path,
        "from source import classify\n"
        "def test_pos():\n    assert classify(5) == 'pos'\n",
    )
    run = run_pytest(test, tmp_path)
    assert run.collected
    assert run.all_passed
    assert run.passed == 1


def test_run_pytest_reports_failure_with_traceback(tmp_path: Path):
    _, test = _write(
        tmp_path,
        "from source import classify\n"
        "def test_bad():\n    assert classify(5) == 'neg'\n",
    )
    run = run_pytest(test, tmp_path)
    assert run.failed == 1
    assert not run.all_passed
    assert run.failures and run.failures[0].nodeid


def test_run_pytest_collection_error(tmp_path: Path):
    source = tmp_path / "source.py"
    source.write_text(SRC, encoding="utf-8")
    test = tmp_path / "test_source.py"
    test.write_text("import does_not_exist_xyz\n", encoding="utf-8")
    run = run_pytest(test, tmp_path)
    assert not run.collected or run.errors > 0


def test_full_coverage_picks_local_file_not_decoys(tmp_path: Path):
    # Exercises every branch => 100% line and branch of OUR source.py.
    source, test = _write(
        tmp_path,
        "from source import classify\n"
        "def test_all():\n"
        "    assert classify(-1) == 'neg'\n"
        "    assert classify(0) == 'zero'\n"
        "    assert classify(3) == 'pos'\n",
    )
    cov = run_coverage(source, test, tmp_path)
    assert cov.measured
    assert cov.line_pct == 1.0
    assert cov.branch_pct == 1.0


def test_partial_coverage_reports_uncovered_lines(tmp_path: Path):
    source, test = _write(
        tmp_path,
        "from source import classify\n"
        "def test_pos_only():\n    assert classify(3) == 'pos'\n",
    )
    cov = run_coverage(source, test, tmp_path)
    assert cov.measured
    assert 0.0 < cov.line_pct < 1.0
    assert cov.branch_pct < 1.0
