"""The Optimizer Harness: a reflective, LLM-directed hill-climb over the genome.

This is the "mutation mechanism" the project asks for. The genome is structured JSON;
a second Claude Agent SDK agent (the optimizer) reads concrete failure evidence from
the eval harness — surviving mutants, uncovered branches, collection errors — and emits
new candidate genomes as JSON. Candidates are validated, evaluated on the TRAIN split,
and the best is kept only if it beats the incumbent by a margin (a noise guard). Final
improvement is measured on the HELD-OUT TEST split to prove generalization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from claude_agent_sdk import AssistantMessage, TextBlock, query

from .agent import resolve_model
from .eval_harness import EvalResult, evaluate_split
from .genome import BASELINE, Genome
from .paths import PROMPTS_DIR

LogFn = Callable[[str], None]


@dataclass
class OptimizeResult:
    best_genome: Genome
    baseline_train_score: float
    best_train_score: float
    baseline_test: EvalResult
    best_test: EvalResult
    archive: list[dict] = field(default_factory=list)   # [{round, score, genome, rationale}]
    rounds_run: int = 0

    def to_dict(self) -> dict:
        return {
            "best_genome": self.best_genome.to_dict(),
            "baseline_train_score": self.baseline_train_score,
            "best_train_score": self.best_train_score,
            "rounds_run": self.rounds_run,
            "archive": self.archive,
            "baseline_test_aggregate": self.baseline_test.aggregate,
            "best_test_aggregate": self.best_test.aggregate,
        }


async def optimize(
    rounds: int = 3,
    beam: int = 2,
    k_search: int = 1,
    k_final: int = 1,
    model: str | None = None,
    mutation_cap: int = 30,
    patience: int = 2,
    epsilon: float = 0.5,
    concurrency: int = 1,
    on_log: LogFn | None = None,
) -> OptimizeResult:
    """Run the full optimize loop and return baseline-vs-best on the held-out split."""
    log = on_log or (lambda _msg: None)
    model = resolve_model(model)
    meta_prompt = (PROMPTS_DIR / "optimizer_meta.md").read_text(encoding="utf-8")

    async def eval_train(g: Genome) -> EvalResult:
        return await evaluate_split(
            g, "train", model=model, k=k_search,
            mutation_cap=mutation_cap, concurrency=concurrency,
        )

    log("Evaluating baseline on TRAIN ...")
    incumbent = BASELINE
    incumbent_eval = await eval_train(incumbent)
    best_score = incumbent_eval.aggregate["composite"]
    baseline_train_score = best_score
    log(f"  baseline TRAIN composite = {best_score:.2f}")

    archive: list[dict] = [
        {"round": 0, "score": best_score, "genome": incumbent.to_dict(), "rationale": "baseline"}
    ]
    no_improve = 0
    rounds_run = 0

    for r in range(1, rounds + 1):
        rounds_run = r
        log(f"\n=== Round {r}/{rounds} ===")
        candidates = await _propose_candidates(
            meta_prompt, incumbent, incumbent_eval, beam, model, log
        )
        if not candidates:
            log("  no valid candidates this round")
            no_improve += 1
            if no_improve >= patience:
                log("  patience exhausted; stopping")
                break
            continue

        round_best: Genome | None = None
        round_best_eval: EvalResult | None = None
        round_best_score = best_score

        for i, (cand, rationale) in enumerate(candidates, 1):
            ev = await eval_train(cand)
            sc = ev.aggregate["composite"]
            log(f"  candidate {i}: TRAIN composite = {sc:.2f}  ({rationale[:80]})")
            archive.append({"round": r, "score": sc, "genome": cand.to_dict(), "rationale": rationale})
            if sc > round_best_score + epsilon:
                round_best, round_best_eval, round_best_score = cand, ev, sc

        if round_best is not None and round_best_eval is not None:
            improvement = round_best_score - best_score
            incumbent, incumbent_eval, best_score = round_best, round_best_eval, round_best_score
            no_improve = 0
            log(f"  -> accepted new incumbent (+{improvement:.2f}, now {best_score:.2f})")
        else:
            no_improve += 1
            log(f"  -> no candidate beat incumbent by >{epsilon} (no_improve={no_improve})")
            if no_improve >= patience:
                log("  patience exhausted; stopping")
                break

    log("\nEvaluating BASELINE vs BEST on held-out TEST split ...")
    baseline_test = await evaluate_split(
        BASELINE, "test", model=model, k=k_final, mutation_cap=mutation_cap, concurrency=concurrency
    )
    best_test = await evaluate_split(
        incumbent, "test", model=model, k=k_final, mutation_cap=mutation_cap, concurrency=concurrency
    )

    return OptimizeResult(
        best_genome=incumbent,
        baseline_train_score=baseline_train_score,
        best_train_score=best_score,
        baseline_test=baseline_test,
        best_test=best_test,
        archive=archive,
        rounds_run=rounds_run,
    )


async def _propose_candidates(
    meta_prompt: str,
    incumbent: Genome,
    incumbent_eval: EvalResult,
    beam: int,
    model: str | None,
    log: LogFn,
    max_retries: int = 2,
) -> list[tuple[Genome, str]]:
    """Ask the optimizer agent for ``beam`` new genomes; validate + return them."""
    from claude_agent_sdk import ClaudeAgentOptions

    evidence = _build_evidence(incumbent, incumbent_eval)
    user_prompt = (
        f"Here is the evidence about the current genome's performance on the training "
        f"tasks:\n\n```json\n{json.dumps(evidence, indent=2)}\n```\n\n"
        f"Propose {beam} improved candidate genome(s). Return ONLY a JSON array of "
        f"{beam} genome object(s), each with keys: system_prompt, allowed_tools, "
        f"max_turns, effort, coverage_target, rationale."
    )
    options = ClaudeAgentOptions(
        system_prompt=meta_prompt,
        allowed_tools=[],
        setting_sources=[],
        model=model,
        max_turns=1,
        permission_mode="bypassPermissions",
    )

    for attempt in range(1, max_retries + 1):
        text = await _collect_text(user_prompt, options)
        dicts = _extract_json_array(text)
        candidates: list[tuple[Genome, str]] = []
        for d in dicts:
            if not isinstance(d, dict):
                continue
            rationale = str(d.get("rationale", ""))
            try:
                candidates.append((Genome.from_dict(d), rationale))
            except (ValueError, TypeError, KeyError):
                continue  # discard invalid genome
        if candidates:
            return candidates[:beam]
        log(f"  (optimizer returned no parseable genome, attempt {attempt}/{max_retries})")

    return []


async def _collect_text(prompt: str, options) -> str:
    """Collect the optimizer agent's text. Resilient to transient SDK/CLI errors —
    returns whatever text arrived (possibly empty) instead of crashing the whole
    optimize loop; the caller retries on empty output."""
    chunks: list[str] = []
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
    except Exception:
        # Transient SDK error (e.g. overloaded / "error result"); treat as a failed
        # proposal attempt and let _propose_candidates retry.
        return "".join(chunks)
    return "".join(chunks)


def _build_evidence(incumbent: Genome, ev: EvalResult) -> dict:
    """Compact, actionable evidence for the optimizer to reflect over."""
    tasks = []
    for m in ev.measurements:
        tasks.append({
            "task": m.task,
            "composite": m.composite,
            "collected": m.collected,
            "passed": m.passed,
            "failed": m.failed,
            "errors": m.errors,
            "line_cov": round(m.line_cov, 3),
            "branch_cov": round(m.branch_cov, 3),
            "mutation_score": round(m.mutation_score, 3),
            "surviving_mutants": m.surviving_mutants[:6],
            "uncovered_lines": m.uncovered_lines[:12],
            "failures": m.failures[:4],
            "error": m.error,
        })
    return {
        "current_genome": incumbent.to_dict(),
        "aggregate": ev.aggregate,
        "tasks": tasks,
    }


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json_array(text: str) -> list:
    """Best-effort extraction of a JSON array (or single object) from model output."""
    if not text:
        return []
    # 1) try fenced blocks first
    for block in _FENCE_RE.findall(text):
        parsed = _try_parse(block)
        if parsed is not None:
            return parsed
    # 2) try the whole string
    parsed = _try_parse(text)
    if parsed is not None:
        return parsed
    # 3) fall back to the outermost [ ... ] span
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        parsed = _try_parse(text[start : end + 1])
        if parsed is not None:
            return parsed
    return []


def _try_parse(text: str) -> list | None:
    try:
        obj = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return [obj]
    return None
