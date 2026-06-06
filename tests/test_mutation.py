"""Unit tests for the mutation engine.

``generate_mutants`` is pure and fast. ``run_mutation_testing`` is exercised with a
tiny in-temp-dir example to confirm the kill/survive logic end-to-end (it shells out
to pytest, so it is kept minimal).
"""

import ast
from pathlib import Path

from testforge.mutation import generate_mutants, run_mutation_testing


def test_generates_mutants_for_arithmetic():
    mutants = generate_mutants("def f(a, b):\n    return a + b\n")
    assert mutants
    assert any("Add -> Sub" in m.description for m in mutants)
    # Every mutant must be valid, parseable Python.
    for m in mutants:
        ast.parse(m.code)


def test_generates_comparison_mutants():
    mutants = generate_mutants("def f(a, b):\n    return a < b\n")
    assert any("Lt -> GtE" in m.description for m in mutants)


def test_generates_boolean_and_constant_mutants():
    src = "def f(a, b):\n    return a and b\n\nFLAG = True\nLIMIT = 10\n"
    descs = " ".join(m.description for m in generate_mutants(src))
    assert "And -> Or" in descs
    assert "True -> False" in descs
    assert "10 -> 11" in descs


def test_mutants_differ_from_original():
    src = "def f(a, b):\n    return a + b * 2\n"
    for m in generate_mutants(src):
        assert m.code != src


def test_cap_limits_and_samples():
    # Many sites; cap should bound the count.
    src = "def f(x):\n    return " + " + ".join(["x"] * 40) + "\n"
    mutants = generate_mutants(src, cap=5)
    assert len(mutants) <= 5


def test_no_mutable_sites_returns_empty():
    assert generate_mutants("def f(x):\n    return x\n") == []


def test_strings_are_not_mutated():
    mutants = generate_mutants('def f():\n    return "hello"\n')
    assert mutants == []


def test_run_mutation_testing_kills_with_strong_tests(tmp_path: Path):
    src = "def add(a, b):\n    return a + b\n"
    source = tmp_path / "source.py"
    source.write_text(src, encoding="utf-8")
    test = tmp_path / "test_source.py"
    test.write_text(
        "from source import add\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
        "    assert add(0, 0) == 0\n",
        encoding="utf-8",
    )
    result = run_mutation_testing(source, test, tmp_path, cap=10, timeout=60)
    assert result.error is None
    assert result.total >= 1
    assert result.killed >= 1
    # Source is restored afterwards.
    assert source.read_text(encoding="utf-8") == src


def test_run_mutation_testing_detects_weak_tests(tmp_path: Path):
    # Test executes the function but asserts nothing meaningful => mutants survive.
    src = "def add(a, b):\n    return a + b\n"
    source = tmp_path / "source.py"
    source.write_text(src, encoding="utf-8")
    test = tmp_path / "test_source.py"
    test.write_text(
        "from source import add\n"
        "def test_add():\n"
        "    add(2, 3)\n"  # no assertion on the result
        "    assert True\n",
        encoding="utf-8",
    )
    result = run_mutation_testing(source, test, tmp_path, cap=10, timeout=60)
    assert result.error is None
    assert result.survived >= 1  # weak tests let mutants live
