---
name: novasynth-run
description: "Run a NovaSynth evaluation end-to-end as a tree of human-in-the-loop checkpoints, not a fixed script — from inputs (personas / scenarios / system prompt) through triggering calls, per-call auditing, and building the final report. Use when the user wants to run a NovaSynth batch / voice-agent eval, set up or generate scenarios+personas for a run, decide platform-vs-local at any step, or drive the whole loop. This is the ORCHESTRATOR; it delegates deep procedures to /novasynth-assist, /noveum-dataset, /novaeval-scorer, and /novapilot-audit."
trigger: /novasynth-run
---

# NovaSynth run — orchestration & checkpoints

This is **guidelines + checkpoints**, not a monolithic path. Runs are not standardized; they break in ad-hoc ways. So this skill is a **tree**: at each checkpoint you STOP, tell the operator where things stand, and ask which branch to take — including "take a new branch off-tree." **"Operator" / "user" = the human running Claude Code**, not the bot under test.

Two hard rules that override everything below:
- **Never change repo code on your own initiative.** The code here is a small part of a bigger system — the real bug is usually elsewhere. When something breaks, describe the issue *and* a proposed fix, and let the operator decide.
- **Where the mechanism is genuinely case-specific (scorer changes, local call-running, coalescing batches), ASK.** Do not fabricate a command. A wrong command is worse than a checkpoint.

You may use **ultracode** (Workflow / fan-out subagents) freely for any auditing phase.

**This skill leans on `/novasynth-assist` for the analysis work — invoke it (via the Skill tool) rather than re-deriving.** Use it in **Phase 1** to validate scenarios before upload, and in **Phase 3** to audit each call's transcript against the spec and cross-check the platform scorers (it carries the scorer false-pass / false-fail cheatsheet). See the delegation map at the end for the full split.

---

## First thing, every run: set up the two logs

These are **two different files** — do not conflate them.

1. **`RUN_LOG.md` — the traceability log (you hand-write this).** One markdown file for the whole run. **One-liners, not detail.** This is for *traceability*, not reproducibility. It serves two purposes for the operator: (a) after the report ships, skim it to harvest every bug found + how it was squashed, to commit back to the real codebase; (b) come back a week later and instantly recover "where are the scenarios / which dataset fed the final report / what's the current status / how do I recreate it." Log a one-line entry when each of these happens:
   - scenarios/personas created (`"10 scenarios created"`, `"10 more created"`) and **where they were saved**
   - where the runs were saved; where the run audits were saved
   - where the dataset is; the **dataset name/slug on the platform**; which **organization** this run is for
   - where scorers were created; when the dataset was uploaded and under what slug
   - each **bug found and how it was squashed**
   - **which dataset was created vs which dataset fed the final report**, and each change made to the report
   This is *your* prose, not a dump of program output.

2. **Raw execution logs (redirect long-running commands to a file).** Whenever you run the scorer executor or any long NovaEval op, tee/redirect it to a file so the operator can tail progress — the executor has **no progress bar**, and all its progress lines go to **stderr**:
   ```bash
   novaeval executor run --input req.json --output out.json 2> logs/exec_run.log   # then: tail -f logs/exec_run.log
   ```

---

## Cross-cutting rules (apply in every phase)

- **Big JSON → curl to a file, never MCP inline.** Scenarios, personas, calls, batch-analysis payloads are huge and blow the context window. Fetch with `curl ... -H "Authorization: Bearer $KEY" > file.json`, then `jq`; let subagents read the files. (Batch-analysis is ~90k+ chars — always to a file.)
- **Auth.** REST base `https://api.noveum.ai/api/v1`. Key resolution: `$NOVEUM_API_KEY` (from the environment or a local `.env`); for multi-project setups, a project-scoped `<PROJECT>_NOVEUM_API_KEY` var. Never hardcode a key in a file. Some platform routes need **both** the Bearer header and an `apiKeyCookie=$KEY` cookie (the `/noveum-dataset` scripts handle this).
- **Upload only after go-ahead.** If you build a dataset locally and run scorers on it, uploading it to the platform is a checkpoint — get the operator's explicit OK first.
- **Every number in the final report must come only from scorer results.** If any metric is computed elsewhere, alert the operator and ask them to fix it before trusting the report (see Phase 4 for the one known offender).
- **Delegate, don't re-derive:** `/novasynth-assist` (scenario validation + transcript/scorer audit), `/noveum-dataset` (all dataset & audio up/download), `/novaeval-scorer` (create/register a scorer), `/novapilot-audit` (audit a NovaPilot report).

---

## Phase 0 — Preconditions (before any run)

**Checkpoint 0a — branch.** Run `git branch --show-current` and check it was recently forked from `main`. If on `main`, or the branch is stale/unclear:
> "You're on `<branch>`. NovaSynth runs shouldn't happen on `main`. Should I fork a fresh branch from `main`, or is `<branch>` the right one to work on?"
Do not proceed until resolved.

**Checkpoint 0b — project.** Ask which project this run is for. Then verify it exists via the noveum MCP (`getApiV1Projects` / `noveum://projects`). If it is **not** present:
> "Project `<name>` isn't visible on the MCP server. Most likely the MCP is configured with the wrong API key. Want to check the key before we continue?"
Do not proceed until the project is confirmed. Log the org + project in `RUN_LOG.md`.

---

## Phase 1 — Inputs (personas, scenarios, system prompt)

Running any call needs **three** things: **personas**, **scenarios**, and the **bot's system prompt**.

**Checkpoint 1a — inventory.** For each of the three, do we already have it? If any is missing, ask the operator to provide it or confirm we should generate it.

**Checkpoint 1b — generating scenarios (the preferred path).** Prefer the **platform / NovaSynth API (via MCP)** over local generation. The preferred flow:
1. Use the platform to **create the scenarios** first.
2. **Fetch them to a file** (curl, not MCP inline).
3. **Fan out subagents (one per scenario) to audit the scenarios against the system prompt** — do they make sense for this bot? Fix any that don't. (This is `/novasynth-assist validate` — schema + reachability + intent-match + coverage-tag checks. It caught a broken scenario last time.)
4. **Find the gaps** — what kinds of scenarios are *missing* for full coverage.
5. **Author the missing scenarios** to the **JSON schema designed in the NovaEval repo** (see below).
6. **Upload personas + scenarios** back to the platform.

**Upload-direction rule (do not violate):** the platform may hold **more** data than local, but never **less**. So you **upload** local additions up to the platform — you never let an upload *downgrade* what's already there. Diff before you push; if the platform has fields/items local lacks, preserve them.

**Scenario / persona JSON schema (NovaEval repo):**
- Scenario model: `novasynth/core/data_models/scenario.py` — `Scenario{id, name, description, events[], interruptions[], metadata, tags}`. `Event{id, parent_id (tree; null=root), condition (backward-looking "already-said" state, null for root), action (caller **intent only** — no scripted lines/tone), fixed (dead/legacy, always coerced to False — ignore it)}`.
- Persona model: `novasynth/core/data_models/persona.py` — `PersonaV1` (snake_case). `personality_traits` **must** contain exactly one canonical response-length level string verbatim: `'Curt / clipped' | 'Brief / no-nonsense' | 'Regular' | 'Chatty' | 'Rambling / tangents'` (with sample phrases + an `Exchange:` line) — the caller model depends on it.
- **Two shapes coexist:** local Pydantic models are **snake_case**; platform exports are **camelCase** with extra platform-only fields (`organizationId`, `projectId`, `goal`, `generationJobId`, …). Use the right template: the `novasynth/demo/data/*.json` examples mirror the in-repo Pydantic schema; a persona/scenario JSON exported from the platform mirrors the camelCase shape.
- Local generators (fallback, **not** zero-config — they need a model instance + `GEMINI_API_KEY`): `novasynth.generate_personas` / `novasynth.generate_scenarios`; tree-driven variant `scenario_from_tree.py`. Runnable call-site template: `novasynth/scripts/batch_text_conversation_grid.py`.

Log to `RUN_LOG.md`: how many scenarios/personas created, where saved, what was uploaded and under what name.

---

## Phase 2 — Runs

Two run types: **LiveKit** (LiveKit credentials) and **PSTN** (real phone-number calls).

**Checkpoint 2a — where to run.** **Trigger on the platform by default** (NovaSynth batch runs). Only if something is **breaking on the platform** and the platform genuinely can't do what's needed:
> "The platform run is failing on `<X>`. Do you want me to run these calls locally instead?"
Run locally **only with that explicit permission**. (Local call-running goes through the `novasynth` telephony/LiveKit runners; the exact runner is case-specific — confirm which one with the operator rather than guessing.)

**Checkpoint 2b — persona × scenario pairing.** When running N calls over M scenarios and K personas, **pick the apt personas per scenario** — e.g. the **top 2** that fit each scenario. Two pairing rules:
- **Personas must not conflict with the scenario.** If a persona contradicts what the scenario needs, **do not run that pair.**
- You will refine this after Phase 3 reads (a pairing can look fine on paper and still produce a nonsensical call).

Log where the runs were saved.

---

## Phase 3 — Per-call audit (one subagent per call)

First **fetch the calls + transcripts + per-call scorer results to files** — don't re-invent this; `/novasynth-assist` Step 5 has the REST quirks (`runs/{id}` needs `projectId`; the batch-analysis payload is huge → always to a file).

**Fan out one subagent per call** — this checks all calls quickly and comprehensively without flooding your context. Give each subagent the transcript, the persona, the scenario, and the per-call scorer results. Two independent judgments (this is a **judgment call — no heuristics**):

**3a — Is the transcript sensible, given our bot's role as a *synthetic user* with this persona in this scenario?**
- **Does our bot follow the scenario?** If not → **rerun** the call.
- **Is our bot over-spilling information?** A known failure: the sim bot *sees* the scenario and tries to steer the real call toward it. That is **not desirable** — the caller should behave naturally, not narrate the scenario. Flag over-spill.
- **Does the persona conflict with the scenario in practice?** If so, don't keep running that pair (feeds back into Checkpoint 2b).

**3b — Scorer cross-check.** Read the scorers **and their reasonings**: did they actually catch the issues in the transcript? Are they working properly? Use `/novasynth-assist` here — it carries the scorer false-pass / false-fail cheatsheet (LLM judges under-penalize hard gates → false PASS; `item_summary = -1` / audio scorers `= -1` / low CSAT on a refusal → not bot faults; miscalibrated pitch band → false fail).

**Checkpoint 3c — scorers misbehaving.** If a scorer is **not working properly** (missing a real issue, or firing on a non-issue), **do not silently patch it** — alert the operator and ask for guidance:
> "`<scorer>` scored `<X>` on call `<id>` but the transcript shows `<Y>`. It looks like it's mis-scoring `<gate>`. How do you want to handle it — override, re-run, or change the scorer?"

Log where the run audits were saved, and every bug found + how it was squashed.

---

## Phase 4 — The NovaSynth report

**Checkpoint 4a — platform report vs local report.**
- **Single batch, everything clean, no changes needed → trigger the report on the platform.** No reason to run locally.
- **Run locally (NovaEval) when** any of: there are **custom scorers**, **multiple batches** need coalescing into one dataset, or you need to **remove** something from the report. Scorer changes are ad-hoc — before building, ask:
> "Any scorer changes for this report — new scorers, removing some, or custom ones?"
(New scorers → `/novaeval-scorer`. Running scorers locally → the **scorer executor**, below.)

**Running scorers locally — the scorer executor.** `novaeval executor run --input <request.json> --output <results.json>` (`src/novaeval/executor/scorer_executor.py`). It takes an **`ExecutorRequest` JSON with inline `items` + `scorers` + `llm_config`** — **not** a dataset path, and it has **no `categories` argument**. It writes results to the local `--output` file only (persisting to the platform is a separate step → `/noveum-dataset`'s `upload_scorer_results.py`). Redirect stderr to a log file (above) for progress.

**Report prerequisites (must hold before rendering):**
1. **`item_summary` must be populated on every item** — this is what gives the report its per-call summaries. It is a **post-run scorer**: run it **via the executor alongside the other scorers** (it reads their results). It **cannot be run standalone** (it errors / defaults to 10.0 with no peers). The renderer reads the summary prose from the scorer result's **`reasoning`** field — if it's empty the report prints "No summary available."
2. **Key Observations & Notes** (the end section) is **required** for PDF/MD render — supply `--observations-json <file>` or set `GEMINI_API_KEY` (auto-generates 4–6 bullets via `gemini-3-flash-preview`).
3. **`categories.json`** — groups scorers into report columns and, crucially, **decides which scorers gate call success**. Get it from the platform / MCP, or ask the operator; if none exists, **scope one yourself** (it's just deciding which scorers determine call success). **Hard requirement:** it must contain a category titled exactly **`"Affects Call Success"`** or the loader raises. Scorer ids are matched with the trailing `_scorer` stripped. Template: `novasynth/reporting/examples/everestfleet_report_categories.json`.

**The input shape decides the renderer — and the report *shape*. Pick deliberately:**
```bash
pip install 'novaeval[novasynth-report]'   # reportlab, once
```
- **Single batch on the platform → `--batch-run-id`** reaches the **per-item** renderer (each call = its own row with a per-call summary + scorer tables) and is the only route that supports `--output-md` / `--format json`:
  ```bash
  novaeval novasynth report --batch-run-id <ID> --project-id <PROJ> --org <ORG> \
    --categories-json cats.json --observations-json obs.json \
    --output report.pdf --output-md report.md
  ```
- **Coalesced / multi-batch local dataset → `--dataset-path` (or `--dataset-slug`).** This is the user's main reason to render locally, and it does **not** map to a single `--batch-run-id`:
  ```bash
  novaeval novasynth report --dataset-path coalesced.json \
    --categories-json cats.json --observations-json obs.json --output report.pdf
  ```
  **Know what you get:** this route goes through a **different, trace-grouped renderer** (`novasynth/reporting/path_1_2`, grouped by `source_trace_id`) — **not** the per-item report, and it does **not** honor `--output-md` / `--format json`.
- **Checkpoint 4a-render (ASK when they conflict):** if the operator wants the **per-item** report *shape* over a **coalesced** dataset, those pull in opposite directions (per-item needs a batch-run-id; a coalesced dataset forces the trace-grouped renderer). Don't guess — surface it:
  > "A coalesced multi-batch dataset renders through the trace-grouped report (grouped by call), not the per-item report. Is the trace-grouped shape fine, or do you need the per-item report — in which case we render per batch and combine?"
  The prerequisites below (item_summary reasoning field, required Key Observations, the `Affects Call Success` gate) are verified for the **per-item** (`--batch-run-id`) renderer; if you go trace-grouped, confirm each still behaves as expected on a first render.

**Checkpoint 4b — screenshot the PDF and check for defects.** Render, then **screenshot the PDF and look at it**:
- **No empty tables/columns.** If a section's scorers didn't run (e.g. latency), don't present an empty table — remove it. The per-item Metrics Evaluation section auto-drops empty columns, but **verify the fixed latency/dynamics summary rows** — those always print.
- **Formatting/pagination.** Catch orphaned headings — e.g. a "Transcript" heading stranded on one page with the transcript starting on the next.

**Checkpoint 4c — numbers-hygiene (the metrics rule, concretely).** Confirm **every number comes only from scorer results.** Known offender: the report's **aggregate latency rows are computed from `item['latency_meta']`, not from a scorer result** — so "Avg Response Latency" can print even with no latency scorer. If you see any metric sourced outside scorer results, **alert the operator and ask them to fix it** before the report is trusted.

**Checkpoint 4d — upload.** If you built the dataset locally, uploading it (and scorer results) to the platform is a checkpoint — get the go-ahead, then use `/noveum-dataset`. Log the final dataset slug and note in `RUN_LOG.md` **which dataset fed the final report**.

---

## Delegation map

| Need | Use |
|---|---|
| Validate scenarios; audit transcripts + scorer verdicts | `/novasynth-assist` |
| Download/upload dataset items, scorer results, audio | `/noveum-dataset` |
| Create / register a new scorer in NovaEval | `/novaeval-scorer` |
| Audit a NovaPilot report's recommendations | `/novapilot-audit` |
| Run scorers locally | `novaeval executor run` (scorer executor) |
| Build the report locally | `novaeval novasynth report --batch-run-id ...` |
