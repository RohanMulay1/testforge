"""Unit tests for the Genome (pure, no SDK / no API key needed)."""

import json

import pytest

from testforge.genome import (
    BASELINE,
    DEFAULT_TOOLS,
    MAX_MAX_TURNS,
    MIN_MAX_TURNS,
    REQUIRED_TOOLS,
    TOOL_RUN_PYTEST,
    Genome,
)


def test_baseline_is_valid_and_weak():
    # Arrange / Act
    g = BASELINE.validated()

    # Assert: baseline is valid and intentionally minimal (short prompt = headroom).
    assert g.system_prompt
    assert len(g.system_prompt) < 400
    assert TOOL_RUN_PYTEST in g.allowed_tools


def test_json_round_trip_is_stable():
    g = BASELINE.evolve(system_prompt="Write thorough tests.", max_turns=15)
    restored = Genome.from_json(g.to_json())
    assert restored.to_dict() == g.to_dict()


def test_max_turns_is_clamped_to_bounds():
    too_high = Genome(system_prompt="x", max_turns=999).validated()
    too_low = Genome(system_prompt="x", max_turns=1).validated()
    assert too_high.max_turns == MAX_MAX_TURNS
    assert too_low.max_turns == MIN_MAX_TURNS


def test_coverage_target_is_clamped():
    assert Genome(system_prompt="x", coverage_target=5.0).validated().coverage_target == 1.0
    assert Genome(system_prompt="x", coverage_target=0.0).validated().coverage_target == 0.60


def test_invalid_effort_falls_back_to_medium():
    assert Genome(system_prompt="x", effort="ultra").validated().effort == "medium"


def test_unknown_tools_are_dropped_and_bash_is_rejected():
    g = Genome(
        system_prompt="x",
        allowed_tools=("Read", "Bash", "NotARealTool", "Write"),
    ).validated()
    assert "Bash" not in g.allowed_tools
    assert "NotARealTool" not in g.allowed_tools
    assert "Read" in g.allowed_tools


def test_required_tools_are_always_added():
    # Start with only Read; validation must re-add the rest of the required set.
    g = Genome(system_prompt="x", allowed_tools=("Read",)).validated()
    for req in REQUIRED_TOOLS:
        assert req in g.allowed_tools


def test_duplicate_tools_are_deduped_preserving_order():
    g = Genome(
        system_prompt="x",
        allowed_tools=("Read", "Read", "Write", "Write"),
    ).validated()
    assert g.allowed_tools.count("Read") == 1
    assert g.allowed_tools.count("Write") == 1


def test_blank_prompt_raises():
    with pytest.raises(ValueError):
        Genome(system_prompt="   ").validated()


def test_from_dict_fills_defaults_from_partial():
    g = Genome.from_dict({"system_prompt": "Only a prompt given."})
    assert g.max_turns == 12
    assert g.allowed_tools == DEFAULT_TOOLS
    assert g.effort == "medium"


def test_render_injects_coverage_target():
    g = Genome(system_prompt="Base.", coverage_target=0.85).validated()
    rendered = g.render_system_prompt()
    assert "85%" in rendered
    assert rendered.startswith("Base.")


def test_evolve_returns_new_validated_instance():
    g1 = Genome(system_prompt="x", max_turns=12).validated()
    g2 = g1.evolve(max_turns=999)
    assert g2 is not g1
    assert g2.max_turns == MAX_MAX_TURNS  # clamped by validation
    assert g1.max_turns == 12  # original unchanged (immutability)


def test_baseline_is_intentionally_minimal():
    # The baseline omits the coverage tool and uses low effort/few turns, giving
    # the optimizer headroom. (Dataclass field defaults remain richer.)
    from testforge.genome import TOOL_MEASURE_COVERAGE
    assert TOOL_MEASURE_COVERAGE not in BASELINE.allowed_tools
    assert BASELINE.effort == "low"
    assert BASELINE.max_turns == 8


def test_from_dict_with_list_tools_from_json():
    # Simulates what the optimizer agent emits (JSON => list, not tuple).
    payload = json.loads('{"system_prompt": "p", "allowed_tools": ["Read", "Write"]}')
    g = Genome.from_dict(payload)
    assert isinstance(g.allowed_tools, tuple)
    assert "Read" in g.allowed_tools
