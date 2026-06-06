# TestForge

**A self-improving unit-test-writing agent, built on the Claude Agent SDK.**

TestForge points an autonomous agent at a Python source file; the agent writes a
pytest suite, runs it, reads its own coverage and failures through custom tools, and
iterates until the suite is green and thorough. A systematic **eval harness** scores
how good those suites are, and an **optimizer** uses those scores to evolve the agent's
prompt + config until it measurably improves — proven on a held-out set of tasks the
optimizer never saw.

It is built **on the Agent SDK** (`claude_agent_sdk`), not on raw Anthropic API calls:
the agent loop, tool execution, and context management are the SDK's; we add a domain,
custom tools, an evaluation methodology, and an optimization loop on top.

---

## The three pillars

### 1. A working agent (`src/testforge/agent.py`, `tools.py`, `sandbox.py`)

A test-writing agent driven by the SDK's `query()` loop. We never write a
`while stop_reason == "tool_use"` loop — the SDK runs it. The agent has:

- **Built-in SDK tools** (zero tool-execution code from us): `Read`, `Write`, `Edit`,
  `Glob`, `Grep`.
- **Two custom in-process tools** defined with `@tool` and served via
  `create_sdk_mcp_server` — the SDK's first-class extension point:
  - `run_pytest` → runs the generated suite and returns a **structured** report
    (pass/fail counts, failing nodeids, tracebacks).
  - `measure_coverage` → returns line/branch coverage plus the **exact uncovered line
    numbers and partial branches**, so the agent knows what to test next.
- **Raw `Bash` is deliberately disallowed.** All execution flows through the two
  sandboxed tools, which keeps runs deterministic and gives the model structured signal
  instead of raw stdout to scrape.

Each task runs in an isolated temp directory (`sandbox.py`); the agent's `cwd` is pinned
there and `setting_sources=[]` keeps your global `~/.claude` config out of eval runs.

The loop the agent performs: *read source → write `test_*.py` → `run_pytest` → fix
failures → `measure_coverage` → add tests for uncovered branches → repeat.*

### 2. An eval harness (`eval_harness.py`, `metrics.py`, `mutation.py`)

The harness recomputes **every** number itself — it never trusts what the agent claims.
For each task it measures:

| Metric | How | Why it matters |
| --- | --- | --- |
| **Validity gate** | `pytest` collects? all tests pass? | A red/invalid suite has no measurable quality → score 0 |
| **Line coverage** | `coverage.py --branch` | Did tests execute the code? |
| **Branch coverage** | `coverage.py --branch` | Did tests exercise both sides of each decision? |
| **Mutation score** | custom AST engine (`mutation.py`) | **Do the tests actually *assert behavior*?** |
| Efficiency | SDK `ResultMessage` (`num_turns`, `total_cost_usd`) | Cost of getting there (secondary) |

**Mutation testing is the centerpiece metric.** Coverage only proves code *ran*; it
says nothing about whether the tests would *notice* if the code were wrong. The mutation
engine injects small semantic faults one at a time — `+`→`-`, `<`→`>=`, `and`→`or`,
`True`→`False`, constant tweaks — re-runs the suite, and counts how many mutants the
tests **kill** (cause to fail). A suite that calls every function but asserts nothing
gets high coverage and a *low* mutation score. That's exactly the failure mode we want
the optimizer to fix.

**Composite score (0–100), per task:**

```
gate    = 1 if (suite collects AND all tests pass) else 0
quality = 0.40·mutation_score + 0.30·branch_cov + 0.20·line_cov + 0.10·pass_validity
score   = 100 · gate · quality
```

The split is fixed in `tasks/manifest.json`: **6 train** tasks the optimizer learns
from, **4 held-out test** tasks used only for the final before/after.

### 3. An optimizer harness (`optimizer.py`, `prompts/optimizer_meta.md`)

A reflective, **LLM-directed hill-climb** over the *genome* — the agent's tunable DNA:

```python
Genome(system_prompt, allowed_tools, max_turns, effort, coverage_target)
```

(There is no `temperature` knob — `ClaudeAgentOptions` doesn't expose one — so the
genome tunes `effort`, the SDK's reasoning-budget control, instead.)

The loop:

1. Evaluate the **baseline** genome on TRAIN; collect concrete evidence — surviving
   mutants, uncovered lines, failing nodeids.
2. **Reflect:** a *second Claude Agent SDK agent* (the optimizer) reads that evidence
   and emits `beam` new candidate genomes as strict JSON.
3. **Validate + clamp** each candidate (`Genome.validated()`): bounds enforced, unknown
   tools dropped (Bash can't sneak in), required tools re-added.
4. **Evaluate** candidates on TRAIN; the incumbent is replaced only if a candidate beats
   it by a margin `epsilon` (a noise guard).
5. Repeat for `rounds`, with early-stop after `patience` rounds of no gain.
6. **Final:** evaluate baseline vs. best on the **held-out TEST split** → before/after.

This is the requested "mutation mechanism": the genome is structured data, and an LLM
performs **directed mutations on it** grounded in failure evidence — not random search.
Guardrails keep every proposed genome valid and within bounds.

---

## Results

> Generated by `python scripts/run_optimize.py` (held-out TEST split, which the
> optimizer never trains on). Full artifacts in `runs/`: `best_genome.json`,
> `optimize_result.json`, `report.md`.

<!-- RESULTS_START -->

_Run: `claude-haiku-4-5`, 6 train / 4 held-out tasks, 2 rounds × beam 2._

**Training signal — the optimizer measurably improved the agent it was optimizing:**

| | Composite (0–100) |
| --- | ---: |
| Baseline genome (TRAIN) | **82.22** |
| Optimized genome (TRAIN, after 2 rounds) | **99.45**  (**+17.23**) |

**What the optimizer changed** — it co-optimized *prompt and config* from evidence,
not random search. Starting from a deliberately minimal baseline genome, it produced:

| Gene | Baseline | Optimized | Why (from the evidence it was shown) |
| --- | --- | --- | --- |
| `max_turns` | 8 | **18** | some suites hit the turn cap and were left incomplete → tripped the pass gate (score 0); more turns fixed them |
| `effort` | low | **high** | harder tasks needed more reasoning per turn |
| `coverage_target` | 0.6 | **0.9** | raised the bar shown to the agent |
| tools | no coverage tool | **+`measure_coverage`** (+Glob/Grep) | surviving mutants / uncovered lines → the agent needed coverage feedback to iterate |
| `system_prompt` | "write tests, make them pass" | a **mutation-killing strategy** | low mutation scores → assert *exact* values, parametrize `C-1/C/C+1` around every constant, verify exception type **and** message, loop on `measure_coverage` |

That `system_prompt` rewrite is the heart of it: the optimizer read the **surviving
mutants** and concluded the agent had to *assert behavior*, not just execute code —
which is exactly the mutation-score term the composite weights most.

**Held-out generalization (4 unseen tasks).** A single run per task (`k=1`) is too noisy
to read on only 4 tasks: one suite that trips the pass/collect gate swings a task between
0 and 100, i.e. ±25 aggregate points. The `k=1` optimize run showed this directly —
`date_range` went 0→100 (optimizer fixed a baseline gate failure) while `csv_parser`
flipped 100→0 on a single bad run, canceling out. The honest comparison averages
`k=3` runs/task to wash out that variance:

<!-- HELDOUT_K3 -->
_Clean held-out comparison (`scripts/run_compare.py --best runs/best_genome.json --split test --k 3`)
is being generated; see `runs/compare_test_k3.md`._
<!-- /HELDOUT_K3 -->

**How to read it:** the baseline genome is intentionally minimal — the optimizer's job is
to discover, from evidence, the prompt + config that lift the composite, chiefly by
pushing the agent from "code that runs" to "behavior that's asserted" (mutation score).
Full artifacts: `runs/best_genome.json`, `runs/optimize_result.json`, `runs/report.md`.
<!-- RESULTS_END -->

---

## Quickstart

```bash
# 1. Install (Python >= 3.10). Also needs the Claude Code CLI on PATH for the SDK.
pip install -e .

# 2. Authenticate the SDK (either works):
#    - export ANTHROPIC_API_KEY=...    (copy .env.example -> .env)
#    - or be logged into the Claude Code CLI

# 3. Run the harness unit tests (no API key needed):
python -m pytest tests/ -q

# 4. Smoke-test the agent on one task (writes + measures a suite):
python scripts/run_agent.py stack
python scripts/run_agent.py path/to/any_module.py     # or any local .py file

# 5. Baseline numbers on the held-out split:
python scripts/run_eval.py --genome baseline --split test

# 6. The headline: optimize, then compare baseline vs best on held-out tasks:
python scripts/run_optimize.py --rounds 3 --beam 2
```

### Useful flags

| Flag | Where | Meaning |
| --- | --- | --- |
| `--rounds`, `--beam` | optimize | search budget (rounds × candidates/round) |
| `--k-search`, `--k-final` | optimize | runs/task during search vs. final report (averages out run-to-run variance) |
| `--mutation-cap` | all | max mutants/task (caps cost; default 30) |
| `--epsilon`, `--patience` | optimize | acceptance margin and early-stop |
| `--concurrency` | eval/optimize | parallel task evaluations |
| `--keep` | run_agent | keep the sandbox dir to inspect generated tests |

**Cost/time:** the optimizer makes many agent runs (baseline + every candidate × every
train task, plus the final test eval). Keep it cheap with small `--rounds`/`--beam`,
`--k-search 1`, and a lower `--mutation-cap`. A full `--rounds 3 --beam 2` run takes
tens of minutes and real tokens; the smoke/eval commands are much cheaper.

---

## Project layout

```
src/testforge/
  genome.py        # the tunable agent config (immutable, validated) + BASELINE
  tools.py         # @tool run_pytest / measure_coverage  -> create_sdk_mcp_server
  agent.py         # genome -> ClaudeAgentOptions -> query();  captures transcript + stats
  sandbox.py       # per-task isolated temp dir + task loading
  execution.py     # subprocess layer: run pytest (JUnit XML) + coverage (JSON)
  mutation.py      # AST mutation engine + mutant-kill runner
  metrics.py       # composite scoring + aggregation
  eval_harness.py  # run a genome over a split -> independent measurements
  optimizer.py     # reflective beam hill-climb; the optimizer (meta) agent
  reporting.py     # Markdown eval tables + before/after
tasks/             # 10 deterministic source modules + manifest (6 train / 4 test)
prompts/           # optimizer_meta.md (the reflection meta-prompt + genome schema)
scripts/           # run_agent.py, run_eval.py, run_optimize.py
tests/             # unit tests for the harness itself
```

## Design decisions & honesty notes

- **Why test-writing?** It has the richest agentic loop *and* the most objective
  metrics. "Did the tests pass and catch bugs?" is far less hand-wavy than judging a
  generated README.
- **Mutation score over raw coverage.** Optimizing for coverage alone rewards tests that
  execute code without asserting anything. Mutation score is what makes "good" mean
  *good*.
- **Held-out evaluation.** Improvement is reported on tasks the optimizer never saw, so
  the numbers reflect a better *agent*, not prompt-overfitting to specific tasks.
- **Model held fixed** across baseline and best (`TESTFORGE_MODEL`, default
  `claude-sonnet-4-6`) so any gain is attributable to the prompt+config, not a model
  swap.
- **What's unit-tested vs. live-validated.** The deterministic logic (genome, metrics,
  mutation engine, scoring, coverage selection, reporting) has direct unit tests. The
  SDK/API-bound modules (agent, optimizer, eval orchestration) are validated by the live
  `run_agent`/`run_optimize` commands rather than mocked unit tests.
