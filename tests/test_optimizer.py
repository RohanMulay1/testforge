"""Unit tests for the optimizer's pure helpers (no SDK / API needed)."""

from testforge.eval_harness import EvalResult
from testforge.genome import BASELINE, Genome
from testforge.metrics import TaskMeasurement
from testforge.optimizer import _build_evidence, _extract_json_array


def test_extract_plain_json_array():
    text = '[{"system_prompt": "a"}, {"system_prompt": "b"}]'
    out = _extract_json_array(text)
    assert len(out) == 2
    assert out[0]["system_prompt"] == "a"


def test_extract_from_fenced_block():
    text = 'Here you go:\n```json\n[{"system_prompt": "x"}]\n```\nthanks'
    out = _extract_json_array(text)
    assert out == [{"system_prompt": "x"}]


def test_extract_single_object_wrapped_to_list():
    out = _extract_json_array('{"system_prompt": "solo"}')
    assert out == [{"system_prompt": "solo"}]


def test_extract_embedded_array_with_prose():
    text = 'I propose: [{"system_prompt": "p", "max_turns": 10}] done.'
    out = _extract_json_array(text)
    assert out[0]["max_turns"] == 10


def test_extract_garbage_returns_empty():
    assert _extract_json_array("no json here") == []
    assert _extract_json_array("") == []


def test_extracted_dicts_build_valid_genomes():
    text = '[{"system_prompt": "Strong tests.", "max_turns": 99, "effort": "bogus"}]'
    dicts = _extract_json_array(text)
    g = Genome.from_dict(dicts[0])
    assert g.max_turns == 25      # clamped
    assert g.effort == "medium"   # invalid -> default


def test_build_evidence_is_compact_and_actionable():
    ms = [
        TaskMeasurement(
            task="stack", collected=True, passed=4, line_cov=0.9, branch_cov=0.8,
            mutation_total=10, mutation_killed=6,
            surviving_mutants=["L5: Compare Lt -> GtE (tests still pass)"],
            uncovered_lines=[12, 13],
        )
    ]
    ev = EvalResult(split="train", genome=BASELINE, measurements=ms, model="m")
    evidence = _build_evidence(BASELINE, ev)
    assert "current_genome" in evidence
    assert "aggregate" in evidence
    assert evidence["tasks"][0]["task"] == "stack"
    assert evidence["tasks"][0]["surviving_mutants"]
