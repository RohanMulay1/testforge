"""Custom in-process tools for the test-writing agent.

These are the SDK's first-class extension point: Python functions decorated with
``@tool`` and served via ``create_sdk_mcp_server``. They give the agent **structured**
feedback (pass/fail counts, tracebacks, uncovered line numbers) instead of raw stdout,
and they confine all code execution to the task's sandbox directory.

Because in-process MCP tools run inside *our* Python process (not the agent's working
directory), the server is built by a factory that closes over the sandbox path, so
each agent run gets tools bound to its own isolated directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from .execution import run_coverage, run_pytest

SERVER_NAME = "testforge"


def build_testforge_server(sandbox_dir: str | Path, source_filename: str = "source.py") -> Any:
    """Return an in-process MCP server whose tools operate inside ``sandbox_dir``."""
    sandbox = Path(sandbox_dir)

    def _resolve_test_path(args: dict[str, Any]) -> Path | None:
        given = args.get("test_path")
        if given:
            p = Path(given)
            return p if p.is_absolute() else sandbox / p
        candidates = sorted(sandbox.glob("test_*.py"))
        return candidates[0] if candidates else None

    @tool(
        "run_pytest",
        "Run the generated pytest file and return a structured pass/fail report "
        "with tracebacks. Call this after writing or editing tests. "
        "Optional arg 'test_path' (defaults to the test_*.py file in the working dir).",
        {"test_path": str},
    )
    async def run_pytest_tool(args: dict[str, Any]) -> dict[str, Any]:
        test_path = _resolve_test_path(args)
        if test_path is None or not test_path.exists():
            return _text({"error": "no test file found; write test_<module>.py first"})
        run = run_pytest(test_path, sandbox)
        return _text({
            "collected": run.collected,
            "passed": run.passed,
            "failed": run.failed,
            "errors": run.errors,
            "skipped": run.skipped,
            "num_tests": run.num_tests,
            "all_passed": run.all_passed,
            "failures": [
                {"nodeid": f.nodeid, "message": f.message, "traceback": f.traceback[:1200]}
                for f in run.failures
            ],
        })

    @tool(
        "measure_coverage",
        "Measure line and branch coverage of the source module produced by the tests, "
        "returning the exact uncovered line numbers and partially-covered branches so "
        "you know what to test next. Optional arg 'test_path'.",
        {"test_path": str},
    )
    async def measure_coverage_tool(args: dict[str, Any]) -> dict[str, Any]:
        test_path = _resolve_test_path(args)
        if test_path is None or not test_path.exists():
            return _text({"error": "no test file found; write test_<module>.py first"})
        source_path = sandbox / source_filename
        cov = run_coverage(source_path, test_path, sandbox)
        if not cov.measured:
            return _text({"error": cov.error or "coverage could not be measured"})
        return _text({
            "line_pct": round(cov.line_pct, 4),
            "branch_pct": round(cov.branch_pct, 4),
            "uncovered_lines": cov.uncovered_lines,
            "partial_branches": cov.partial_branches,
        })

    return create_sdk_mcp_server(
        name=SERVER_NAME,
        version="0.1.0",
        tools=[run_pytest_tool, measure_coverage_tool],
    )


def _text(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}
