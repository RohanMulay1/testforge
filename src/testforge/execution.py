"""Subprocess execution layer: run pytest and coverage in isolation, return
structured results.

Shared by the agent's custom tools (tools.py), the eval metrics (metrics.py), and
the mutation runner (mutation.py) so there is a single, robust place that knows how
to invoke pytest/coverage and parse their output. We use pytest's built-in JUnit
XML and coverage.py's JSON output rather than scraping stdout — both are stable,
machine-readable formats that need no third-party plugins.
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TIMEOUT = 120


@dataclass
class Failure:
    nodeid: str
    message: str
    traceback: str


@dataclass
class PytestRun:
    returncode: int
    collected: bool          # did the test file import & collect without error?
    passed: int
    failed: int
    errors: int
    skipped: int
    failures: list[Failure] = field(default_factory=list)
    stdout: str = ""

    @property
    def num_tests(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def all_passed(self) -> bool:
        return self.collected and self.failed == 0 and self.errors == 0 and self.passed > 0


@dataclass
class CoverageResult:
    line_pct: float          # 0..1
    branch_pct: float        # 0..1 (1.0 when the module has no branches)
    uncovered_lines: list[int] = field(default_factory=list)
    partial_branches: list[int] = field(default_factory=list)
    measured: bool = True
    error: str | None = None


def run_pytest(test_path: str | Path, cwd: str | Path, timeout: int = DEFAULT_TIMEOUT) -> PytestRun:
    """Run a single test file and return a structured result via JUnit XML."""
    cwd = Path(cwd)
    test_path = Path(test_path)
    xml_path = cwd / "_tf_report.xml"
    if xml_path.exists():
        xml_path.unlink()

    cmd = [
        sys.executable, "-m", "pytest", str(test_path),
        f"--junit-xml={xml_path}", "-q", "-p", "no:cacheprovider",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        stdout = proc.stdout + proc.stderr
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        return PytestRun(
            returncode=-1, collected=False, passed=0, failed=0, errors=1, skipped=0,
            failures=[Failure("<timeout>", "pytest timed out", "")],
            stdout="pytest timed out",
        )

    if not xml_path.exists():
        # No report => collection failed hard (exit 2/3/4) or no tests (exit 5).
        collected = returncode == 5  # 5 = no tests collected but file imported
        return PytestRun(
            returncode=returncode, collected=collected, passed=0, failed=0,
            errors=0 if collected else 1, skipped=0,
            failures=[] if collected else [Failure("<collection>", _tail(stdout), stdout)],
            stdout=stdout,
        )

    run = _parse_junit(xml_path, returncode, stdout)
    xml_path.unlink(missing_ok=True)
    return run


def run_coverage(
    source_path: str | Path,
    test_path: str | Path,
    cwd: str | Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> CoverageResult:
    """Measure line + branch coverage of ``source_path`` produced by ``test_path``."""
    cwd = Path(cwd)
    source_abs = Path(source_path).resolve()
    data_file = cwd / "_tf_cov"
    json_path = cwd / "_tf_cov.json"
    for p in (data_file, json_path):
        if p.exists():
            p.unlink()

    # Restrict measurement to exactly our source file. Using the absolute path (not a
    # "*source.py" glob) avoids matching unrelated files named source.py in site-packages.
    run_cmd = [
        sys.executable, "-m", "coverage", "run", "--branch",
        f"--data-file={data_file}", f"--include={source_abs}",
        "-m", "pytest", str(Path(test_path).name), "-q", "-p", "no:cacheprovider",
    ]
    json_cmd = [
        sys.executable, "-m", "coverage", "json",
        f"--data-file={data_file}", "-o", str(json_path),
    ]
    try:
        subprocess.run(run_cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        proc = subprocess.run(json_cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return CoverageResult(0.0, 0.0, measured=False, error="coverage timed out")

    if not json_path.exists():
        return CoverageResult(0.0, 0.0, measured=False, error=_tail(proc.stderr or proc.stdout))

    result = _parse_coverage_json(json_path, source_abs, cwd)
    for p in (data_file, json_path):
        p.unlink(missing_ok=True)
    return result


def _parse_junit(xml_path: Path, returncode: int, stdout: str) -> PytestRun:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root

    passed = failed = errors = skipped = 0
    failures: list[Failure] = []
    for case in suite.findall("testcase"):
        nodeid = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
        fnode = case.find("failure")
        enode = case.find("error")
        snode = case.find("skipped")
        if fnode is not None:
            failed += 1
            failures.append(Failure(nodeid, fnode.get("message", ""), (fnode.text or "")[:2000]))
        elif enode is not None:
            errors += 1
            failures.append(Failure(nodeid, enode.get("message", ""), (enode.text or "")[:2000]))
        elif snode is not None:
            skipped += 1
        else:
            passed += 1

    # Collection-level errors show up as a synthetic testcase with an <error>.
    collected = not (errors > 0 and passed == 0 and failed == 0 and returncode == 2)
    return PytestRun(
        returncode=returncode, collected=collected, passed=passed, failed=failed,
        errors=errors, skipped=skipped, failures=failures, stdout=stdout,
    )


def _parse_coverage_json(json_path: Path, source_abs: Path, cwd: Path) -> CoverageResult:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    files = data.get("files", {})
    entry = None
    for path, info in files.items():
        # Coverage may report our file as a path relative to the run cwd; resolve
        # both sides and compare exactly so we never pick a same-named decoy.
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        if candidate.resolve() == source_abs:
            entry = info
            break
    if entry is None:
        return CoverageResult(0.0, 0.0, measured=False, error=f"{source_abs.name} not in coverage data")

    summary = entry.get("summary", {})
    line_pct = float(summary.get("percent_covered", 0.0)) / 100.0
    num_branches = summary.get("num_branches", 0) or 0
    covered_branches = summary.get("covered_branches", 0) or 0
    branch_pct = (covered_branches / num_branches) if num_branches else 1.0

    uncovered = sorted(int(x) for x in entry.get("missing_lines", []))
    partial = sorted({int(b[0]) for b in entry.get("missing_branches", []) if b})
    return CoverageResult(
        line_pct=line_pct, branch_pct=branch_pct,
        uncovered_lines=uncovered, partial_branches=partial,
    )


def _tail(text: str, n: int = 1500) -> str:
    text = text or ""
    return text[-n:]
