"""The Genome: the agent configuration the optimizer mutates.

A genome is the full, structured "DNA" of the test-writing agent: its system prompt
plus the SDK config knobs the optimizer is allowed to tune. It is immutable
(``frozen=True``) per the project's coding-style rules — mutating means producing a
new copy via :meth:`Genome.evolve` or :func:`Genome.from_dict`.

This module deliberately has **no top-level Claude Agent SDK import** so the genome
validation/serialization logic stays unit-testable without the SDK installed or an
API key present. The SDK is imported lazily inside :meth:`Genome.to_options`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# --- Tool catalog -----------------------------------------------------------
# Custom in-process tools served by tools.py via create_sdk_mcp_server("testforge").
TOOL_RUN_PYTEST = "mcp__testforge__run_pytest"
TOOL_MEASURE_COVERAGE = "mcp__testforge__measure_coverage"

# The full set of tools a genome may request. The optimizer cannot grant anything
# outside this whitelist — notably raw "Bash" is excluded so all code execution
# flows through the sandboxed custom tools.
ALLOWED_TOOL_CATALOG: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    TOOL_RUN_PYTEST,
    TOOL_MEASURE_COVERAGE,
)

# Tools that must always be present — without these the agent cannot do its job.
REQUIRED_TOOLS: tuple[str, ...] = ("Read", "Write", "Edit", TOOL_RUN_PYTEST)

DEFAULT_TOOLS: tuple[str, ...] = ALLOWED_TOOL_CATALOG

# --- Bounds (guardrails the optimizer cannot exceed) ------------------------
MIN_MAX_TURNS = 5
MAX_MAX_TURNS = 25
VALID_EFFORT: tuple[str, ...] = ("low", "medium", "high")
MIN_COVERAGE_TARGET = 0.60
MAX_COVERAGE_TARGET = 1.0

# --- Baseline (intentionally weak) system prompt ----------------------------
# Kept deliberately minimal so the optimizer has visible headroom to improve.
# This is the single source of truth for the baseline prompt.
BASELINE_SYSTEM_PROMPT = (
    "You write pytest unit tests for a Python source file.\n"
    "Read the file, write tests into a file named test_<module>.py in the same "
    "directory, and make sure they pass."
)


@dataclass(frozen=True)
class Genome:
    """Immutable agent configuration.

    Fields are the levers the optimizer is allowed to mutate:
      - ``system_prompt``   : the instructions (primary lever)
      - ``allowed_tools``   : which tools the agent may use (whitelist-enforced)
      - ``max_turns``       : agent-loop turn budget, clamped to [5, 25]
      - ``effort``          : SDK reasoning-budget knob ("low"|"medium"|"high")
      - ``coverage_target`` : injected into the rendered prompt, clamped to [0.6, 1.0]
    """

    system_prompt: str = BASELINE_SYSTEM_PROMPT
    allowed_tools: tuple[str, ...] = DEFAULT_TOOLS
    max_turns: int = 12
    effort: str = "medium"
    coverage_target: float = 0.9

    # -- construction / serialization ---------------------------------------
    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Genome":
        """Build a validated genome from a (possibly partial/untrusted) dict.

        Missing keys fall back to defaults; the result is always passed through
        :meth:`validated`, so the returned genome obeys every invariant.
        Raises ``ValueError`` on an irreparable genome (e.g. blank prompt).
        """
        tools = data.get("allowed_tools", DEFAULT_TOOLS)
        if isinstance(tools, list):
            tools = tuple(tools)
        raw = Genome(
            system_prompt=str(data.get("system_prompt", BASELINE_SYSTEM_PROMPT)),
            allowed_tools=tuple(tools),
            max_turns=int(data.get("max_turns", 12)),
            effort=str(data.get("effort", "medium")),
            coverage_target=float(data.get("coverage_target", 0.9)),
        )
        return raw.validated()

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "allowed_tools": list(self.allowed_tools),
            "max_turns": self.max_turns,
            "effort": self.effort,
            "coverage_target": self.coverage_target,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_json(text: str) -> "Genome":
        return Genome.from_dict(json.loads(text))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> "Genome":
        return Genome.from_json(Path(path).read_text(encoding="utf-8"))

    def evolve(self, **changes: Any) -> "Genome":
        """Return a new validated genome with the given fields replaced."""
        return replace(self, **changes).validated()

    # -- validation / repair -------------------------------------------------
    def validated(self) -> "Genome":
        """Return a repaired/clamped copy that satisfies all invariants.

        Repairs (never raises) for: out-of-range numeric bounds, invalid effort,
        unknown/duplicate tools, and missing required tools. Raises ``ValueError``
        only for a genome that cannot be salvaged (blank system prompt).
        """
        prompt = self.system_prompt.strip()
        if not prompt:
            raise ValueError("Genome.system_prompt must be non-empty")

        # Filter to the whitelist (drops e.g. "Bash"), dedupe, preserve order.
        seen: set[str] = set()
        tools: list[str] = []
        for t in self.allowed_tools:
            if t in ALLOWED_TOOL_CATALOG and t not in seen:
                seen.add(t)
                tools.append(t)
        # Ensure required tools are present.
        for req in REQUIRED_TOOLS:
            if req not in seen:
                seen.add(req)
                tools.append(req)

        effort = self.effort if self.effort in VALID_EFFORT else "medium"
        max_turns = _clamp_int(self.max_turns, MIN_MAX_TURNS, MAX_MAX_TURNS)
        cov = _clamp_float(self.coverage_target, MIN_COVERAGE_TARGET, MAX_COVERAGE_TARGET)

        return Genome(
            system_prompt=prompt,
            allowed_tools=tuple(tools),
            max_turns=max_turns,
            effort=effort,
            coverage_target=cov,
        )

    # -- rendering / SDK wiring ----------------------------------------------
    def render_system_prompt(self) -> str:
        """The system prompt actually sent to the agent, with the coverage target
        injected so the agent knows the bar it is being held to."""
        target_pct = round(self.coverage_target * 100)
        return (
            f"{self.system_prompt}\n\n"
            f"Aim for at least {target_pct}% line and branch coverage of the source module."
        )

    def to_options(
        self, mcp_servers: dict[str, Any], model: str | None, cwd: str | None = None
    ) -> Any:
        """Map this genome onto a Claude Agent SDK ``ClaudeAgentOptions``.

        Imported lazily so this module stays usable without the SDK installed.
        ``permission_mode="bypassPermissions"`` is safe here because every tool is
        sandboxed (custom tools confine execution to the task temp dir) and raw
        Bash is not in the catalog. ``setting_sources=[]`` prevents the developer's
        global ~/.claude config from leaking into eval runs. ``cwd`` pins the
        built-in Read/Write/Edit tools to the task sandbox.
        """
        from claude_agent_sdk import ClaudeAgentOptions  # lazy

        return ClaudeAgentOptions(
            system_prompt=self.render_system_prompt(),
            allowed_tools=list(self.allowed_tools),
            mcp_servers=mcp_servers,
            max_turns=self.max_turns,
            effort=self.effort,
            model=model,
            permission_mode="bypassPermissions",
            setting_sources=[],
            cwd=cwd,
        )


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def _clamp_float(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


# The baseline genome: deliberately minimal, so the optimizer has real, multi-
# dimensional headroom to improve. It ships the terse prompt, only the bare-minimum
# tools (no measure_coverage — the agent is blind to coverage), low effort, and a
# small turn budget. The optimizer can then discover that adding the coverage tool,
# raising effort/turns, and sharpening the prompt all lift quality. This is the
# "before" in every before/after report.
BASELINE = Genome(
    system_prompt=BASELINE_SYSTEM_PROMPT,
    allowed_tools=("Read", "Write", "Edit", TOOL_RUN_PYTEST),
    max_turns=8,
    effort="low",
    coverage_target=0.6,
).validated()
