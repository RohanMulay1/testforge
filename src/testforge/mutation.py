"""A lightweight AST mutation-testing engine.

Mutation testing answers the question coverage cannot: *do the tests actually
assert behavior, or do they just execute lines?* We apply small semantic mutations
to the source (one at a time), re-run the generated tests, and count how many
mutants the tests *kill* (cause to fail). A suite that prints no assertions will
cover lines but kill no mutants.

The engine is pure-Python (``ast`` + ``ast.unparse``) and deterministic, so
``generate_mutants`` is fully unit-testable without any subprocess or API.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .execution import run_pytest

# Operator swap catalogs. Comparison swaps use the logical negation
# (e.g. ``<`` -> ``>=``) so each mutant flips real branch behavior.
_BINOP_SWAPS: dict[type, type] = {
    ast.Add: ast.Sub, ast.Sub: ast.Add,
    ast.Mult: ast.Div, ast.Div: ast.Mult,
    ast.Mod: ast.Mult, ast.FloorDiv: ast.Mult,
}
_CMP_SWAPS: dict[type, type] = {
    ast.Lt: ast.GtE, ast.GtE: ast.Lt,
    ast.Gt: ast.LtE, ast.LtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}
_BOOL_SWAPS: dict[type, type] = {ast.And: ast.Or, ast.Or: ast.And}


@dataclass
class Mutant:
    id: int
    code: str
    description: str
    lineno: int


@dataclass
class _Site:
    apply: Callable[[], None]
    description: str
    lineno: int


@dataclass
class MutationResult:
    total: int
    killed: int
    survived: int
    surviving: list[str]   # human-readable descriptions of survivors (optimizer evidence)
    error: str | None = None

    @property
    def score(self) -> float:
        return (self.killed / self.total) if self.total else 0.0


def generate_mutants(source: str, cap: int = 30) -> list[Mutant]:
    """Generate up to ``cap`` single-point mutants of ``source`` (deterministic).

    When more candidate sites exist than ``cap``, sites are sampled with an even
    stride across the file so mutants are spread out rather than clustered at the top.
    """
    base = ast.parse(source)
    n_sites = len(_collect_sites(base))

    raw: list[Mutant] = []
    for k in range(n_sites):
        tree = ast.parse(source)
        sites = _collect_sites(tree)
        site = sites[k]
        site.apply()
        ast.fix_missing_locations(tree)
        code = ast.unparse(tree)
        if code == source:
            continue  # no-op mutant (e.g. unparse normalized it away)
        raw.append(Mutant(id=k, code=code, description=site.description, lineno=site.lineno))

    if len(raw) <= cap:
        return raw
    stride = len(raw) / cap
    return [raw[int(i * stride)] for i in range(cap)]


def run_mutation_testing(
    source_path: str | Path,
    test_path: str | Path,
    cwd: str | Path,
    cap: int = 30,
    timeout: int = 60,
) -> MutationResult:
    """Apply each mutant to ``source_path`` and re-run ``test_path``; a mutant is
    *killed* if the tests then fail/error. The original source is always restored.

    Precondition: the unmutated tests pass. If they do not, mutation score is
    undefined and we return an error sentinel (the harness gates this out anyway).
    """
    source_path = Path(source_path)
    original = source_path.read_text(encoding="utf-8")

    baseline = run_pytest(test_path, cwd, timeout=timeout)
    if not baseline.all_passed:
        return MutationResult(0, 0, 0, [], error="baseline tests do not pass; mutation score undefined")

    mutants = generate_mutants(original, cap=cap)
    if not mutants:
        return MutationResult(0, 0, 0, [], error="no mutants generated")

    killed = 0
    surviving: list[str] = []
    try:
        for m in mutants:
            source_path.write_text(m.code, encoding="utf-8")
            result = run_pytest(test_path, cwd, timeout=timeout)
            if result.all_passed:
                surviving.append(f"L{m.lineno}: {m.description} (tests still pass)")
            else:
                killed += 1
    finally:
        source_path.write_text(original, encoding="utf-8")

    total = len(mutants)
    return MutationResult(total=total, killed=killed, survived=total - killed, surviving=surviving)


def _collect_sites(tree: ast.AST) -> list[_Site]:
    """Collect mutation sites in deterministic ``ast.walk`` order.

    Because two parses of the same source are structurally identical and ``ast.walk``
    is deterministic, the k-th site here corresponds to the k-th site in any fresh
    parse — which is what lets ``generate_mutants`` apply one mutation per mutant.
    """
    sites: list[_Site] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SWAPS:
            repl = _BINOP_SWAPS[type(node.op)]
            sites.append(_binop_site(node, repl))
        elif isinstance(node, ast.Compare):
            for idx, op in enumerate(node.ops):
                if type(op) in _CMP_SWAPS:
                    sites.append(_compare_site(node, idx, _CMP_SWAPS[type(op)]))
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL_SWAPS:
            sites.append(_boolop_site(node, _BOOL_SWAPS[type(node.op)]))
        elif isinstance(node, ast.Constant):
            site = _constant_site(node)
            if site is not None:
                sites.append(site)
    return sites


def _binop_site(node: ast.BinOp, repl_cls: type) -> _Site:
    def apply(n: ast.BinOp = node, r: type = repl_cls) -> None:
        n.op = r()
    return _Site(apply, f"BinOp {type(node.op).__name__} -> {repl_cls.__name__}", getattr(node, "lineno", 0))


def _compare_site(node: ast.Compare, idx: int, repl_cls: type) -> _Site:
    orig = type(node.ops[idx]).__name__

    def apply(n: ast.Compare = node, i: int = idx, r: type = repl_cls) -> None:
        n.ops[i] = r()
    return _Site(apply, f"Compare {orig} -> {repl_cls.__name__}", getattr(node, "lineno", 0))


def _boolop_site(node: ast.BoolOp, repl_cls: type) -> _Site:
    def apply(n: ast.BoolOp = node, r: type = repl_cls) -> None:
        n.op = r()
    return _Site(apply, f"BoolOp {type(node.op).__name__} -> {repl_cls.__name__}", getattr(node, "lineno", 0))


def _constant_site(node: ast.Constant) -> _Site | None:
    v = node.value
    if isinstance(v, bool):
        new: object = not v
    elif isinstance(v, int):
        new = v + 1
    elif isinstance(v, float):
        new = v + 1.0
    else:
        return None  # skip strings, None, bytes

    def apply(n: ast.Constant = node, nv: object = new) -> None:
        n.value = nv
    return _Site(apply, f"Constant {v!r} -> {new!r}", getattr(node, "lineno", 0))
