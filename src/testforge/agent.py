"""The test-writing agent: drive the Claude Agent SDK agent loop for one task.

This is intentionally thin. We do **not** implement a tool loop, tool execution, or
context management — the SDK's ``query()`` provides all of that. Our job is to map a
:class:`Genome` onto ``ClaudeAgentOptions``, attach the custom tool server bound to
the task sandbox, stream the messages, and capture a compact transcript plus the
efficiency stats from the terminal ``ResultMessage``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .genome import Genome
from .sandbox import Sandbox
from .tools import SERVER_NAME, build_testforge_server

DEFAULT_MODEL = "claude-sonnet-4-6"


def build_prompt(source_filename: str) -> str:
    """The task instruction, parameterized by the source filename so the agent can
    run against any module, not just the bundled ``source.py`` tasks."""
    module = source_filename.removesuffix(".py")
    return (
        f"Write a comprehensive pytest unit-test suite for the Python module "
        f"`{source_filename}` in the current working directory. Save your tests to a "
        f"file named `test_{module}.py` in the same directory. Import the code under "
        f"test with `from {module} import ...`. Use the run_pytest tool to confirm your "
        f"tests pass and the measure_coverage tool to find untested code, then iterate "
        f"until the suite is green and well-covered. Do not edit `{source_filename}`."
    )


def resolve_model(override: str | None = None) -> str:
    return override or os.environ.get("TESTFORGE_MODEL") or DEFAULT_MODEL


@dataclass
class AgentRunResult:
    subtype: str                       # ResultMessage.subtype ("success" | "error_*")
    num_turns: int = 0
    cost_usd: float = 0.0
    tool_calls: int = 0
    transcript: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def transcript_text(self) -> str:
        return "\n".join(self.transcript)


async def write_tests(
    genome: Genome,
    sandbox: Sandbox,
    model: str | None = None,
    max_transcript_chars: int = 6000,
) -> AgentRunResult:
    """Run the agent once against a prepared sandbox; return run stats + transcript."""
    server = build_testforge_server(sandbox.dir, sandbox.task.source_filename)
    options = genome.to_options(
        mcp_servers={SERVER_NAME: server},
        model=resolve_model(model),
        cwd=str(sandbox.dir),
    )

    prompt = build_prompt(sandbox.task.source_filename)
    result = AgentRunResult(subtype="incomplete")
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        result.transcript.append(f"[assistant] {block.text.strip()}")
                    elif isinstance(block, ToolUseBlock):
                        result.tool_calls += 1
                        result.transcript.append(f"[tool] {block.name} {_short(block.input)}")
            elif isinstance(message, ResultMessage):
                result.subtype = message.subtype
                result.num_turns = message.num_turns
                result.cost_usd = message.total_cost_usd or 0.0
                if message.is_error:
                    result.error = message.subtype
    except Exception as exc:  # surface SDK/runtime errors without crashing the harness
        result.error = f"{type(exc).__name__}: {exc}"
        result.subtype = "exception"

    # Trim the transcript so it stays cheap to feed back to the optimizer.
    joined = result.transcript_text
    if len(joined) > max_transcript_chars:
        result.transcript = [joined[-max_transcript_chars:]]
    return result


def _short(value, limit: int = 200) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."
