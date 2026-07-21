# Validate scenarios & audit a NovaSynth run (steps 3S–4)

Two jobs, used at two points in the synthetic branch (`novasynth-generate-run.md`):

1. **Validate scenarios** — before spending call credits (step 3S-b).
2. **Audit the calls + scorers** — after a batch completes (step 3S-e), before you trust the
   dashboard's pass/fail.

The reason this is a named step: generated scenarios are often subtly broken, and the
platform scorers **systematically misjudge hard compliance gates** — a green dashboard can
hide a real failure. Encode the rules below; don't re-derive them.

Base `https://api.noveum.ai/api`, header `Authorization: Bearer $NOVEUM_API_KEY`. Big
payloads (batch analysis, run lists) → `scripts/fetch_to_file.py` (`context-safety.md`).

---

## Job 1 — Validate scenarios (before running)

A scenario is a tree of `events` (`{id, parent_id, action, condition}`) plus `metadata` /
`scenarioType`. Fan out **one subagent per scenario** for large sets. Check each:

1. **Schema** — every event has `id` + `action`, ids unique; `parent_id` is null for the
   root; `condition` is optional (backward-looking; null when gated only by the parent edge);
   every non-root `parent_id` resolves to an existing id (no orphans, no cycles).
2. **Reachability** — every event is reachable from the root via `parent_id`.
3. **Intent match** — the events actually exercise what the scenario `name`/`metadata`/
   `scenarioType` claims (a `red_team`/`edge_case` scenario must contain the adversarial
   event, not happy-path events). This is the check that catches the most broken scenarios.
4. **Coverage gaps** — across the whole set, what scenario *types* are missing for the
   agent's surface area? Author the missing ones (`POST /v1/novasynth/scenarios`).

Report a table `scenario | PASS/FAIL | issue`. **Do not run failing scenarios** — fix or
drop them first.

**Persona × scenario pairing:** when composing the batch, pick the ~2 personas that *fit*
each scenario and **skip contradictory combos** (a persona whose traits fight the scenario
produces a nonsensical call). Prefer explicit `pairs[]` over a blind full matrix.

---

## Jobs 5–7 — Audit the calls + scorers (after running)

### Fetch (mind the quirks)

```bash
python scripts/fetch_to_file.py "/v1/novasynth/batch-runs/<batchRunId>?projectId=<p>" --out /tmp/batch.json
python scripts/fetch_to_file.py "/v1/novasynth/batch-analysis/<batchRunId>"           --out /tmp/analysis.json
```
- **`runs/:id` requires `?projectId=`** (400 without it). Per-run detail:
  `GET /v1/novasynth/runs/:id?projectId=<p>` → `.run.transcriptNormalized`, `.run.traceId`,
  `.run.status`, `.run.error`.
- **Per-run scorer results are NOT on the run** — they live in
  `/tmp/analysis.json` → `analyses[] | select(.runId==<id>) | .scorerResults`.
- A run `status:failed` / `turnCount:0` / `traceId:null` = **infra failure** (re-run), not a
  bot fault.

### Audit each call — one subagent per run

Fan out **one subagent per run** (transcripts are long, often non-English). Give each: the
transcript, its persona, its scenario, and its `scorerResults`. Two judgments (this is a
judgment call — no heuristic):

**A. Is the transcript sensible, given the caller is a *synthetic user* with this persona in
this scenario?**
- Does the caller **follow the scenario**? If not → flag for re-run.
- Is the caller **over-spilling** — narrating or steering toward the scenario instead of
  behaving naturally? Synthetic callers that "see" the scenario and push the agent toward it
  are a known, undesirable artifact — flag it.
- Does the **persona conflict** with the scenario in practice (feeds pairing next round)?
- Remember the `maxCallDurationS` cap (default 300s): a call cut mid-utterance at the cap is
  a harness cutoff, **not** the agent terminating abruptly.

**B. Scorer cross-check — read the *reasoning*, not just the number.** The dashboard's
pass/fail is **not** trustworthy for compliance gating:

**FALSE PASS — LLM-judge scorers under-penalize hard binary gates.** `instruction_adherence`
(and `content_safety`, `answer_refusal`) will *describe* a gate/disclosure violation in
their own reasoning, then call it a "minor deviation" and score 8–9 PASS. A hard gate ("all
qualifying questions before transfer", "identity confirmed before disclosing info") **cannot**
be a soft judge score — when the reasoning admits the violation, override to FAIL.

**FALSE FAIL / not-a-bot-fault — discount these:**
- `item_summary = -1` ("fewer than 3 summary points") → **infra error**, not a bot fault
  (often the thing that flips a run to `failed` despite clean content).
- Audio scorers `= -1` (`mos`, `gibberish`, `stt_efficacy`, `tone_clarity`, `pronunciation`)
  → length-limit / Converse **infra failures**.
- Low `sentiment_csat` / `appropriate_call_termination` on a **refusal or adversarial** call
  is **expected** — a graceful "customer said no" *should* score low on satisfaction without
  being a bot defect.
- `assistant_average_pitch` flagging a female voice against a 100–220 Hz band → miscalibrated
  band, false fail. `assistant_latency` is a TTS/infra metric, not conversational logic.

**TRUST when they fail:** `instruction_adherence` *failing* on a tip-leak/over-promise,
`is_harmful_advice`, `hallucination`, `content_moderation`, `answer_relevancy` on genuine
incoherence — cross-check the reasoning still points at a real agent turn.

**If a scorer is clearly mis-scoring** (missed a real issue, or fired on a non-issue), don't
silently patch it — surface it to the user and ask how to handle it (override / re-run /
change the scorer).

### Report

Per run: one-line issue + agent PASS/FAIL. Then a synthesis separating **hard compliance
failures** (the real story), **soft/debatable** items, and a **scorer-trust note** — every
run the dashboard PASSED that is actually a FAIL, so nobody ships on a green dashboard. Then
proceed to `diagnose-novapilot.md` on the run's `datasetSlug`.
