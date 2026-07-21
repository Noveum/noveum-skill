# Generate synthetic traffic with NovaSynth (step 3, synthetic branch)

Steps 3–4 of the journey build a scored dataset. The main path (`setup-evals.md`) mines
**real** traffic via ETL. This is the alternative when you have little or no production
traffic yet, or you want **targeted adversarial coverage** (edge cases, red-team, refusal
paths): NovaSynth spins up synthetic callers (**personas**) that drive your agent through
**scenarios**, and each call produces a trace + transcript + a scored dataset item — which
then flows into NovaPilot (`diagnose-novapilot.md`) exactly like real traffic.

All endpoints: base `https://api.noveum.ai/api`, header `Authorization: Bearer $NOVEUM_API_KEY`;
prefer the MCP tools if connected. Every path here is under `/v1/novasynth/...`. Poll
cadences + terminal statuses: `api-reference.md`. **Big payloads (batch analysis, run lists)
go to disk** via `scripts/fetch_to_file.py` — see `context-safety.md`.

**Credits + time:** synthetic *voice* calls place real calls and consume credits/minutes —
before triggering a batch, state the estimate (≈ runs × call length) and get user
confirmation, per the global cost rule.

## 3S-a. Register the agent-under-test endpoint

A batch run calls your agent through an **AgentEndpoint** (`endpointId`, required below).

```
POST /v1/novasynth/agent-endpoints        # createAgentEndpointSchema — discriminated on `type`
{ "name": "...", "type": "phone",         # livekit | phone | websocket | pipecat | vapi | retell | elevenlabs_conversational | http_chat
  "phoneNumber": "+1...", "phoneCountryCode": "US" }   # per-type credential fields differ
→ note the returned endpoint id
```
This is distinct from `/v1/novasynth/agent-config` (per-project system prompt + instructions
that feed generation — the prompt context, not the callable endpoint).

## 3S-b. Generate (or create) personas and scenarios

Both generators are **async** — they return a `jobId`; poll the generation job to terminal:

```
POST /v1/novasynth/personas/generate    { "systemPrompt": "<agent prompt>", "count": 3, "instructions": "...", "projectId": "<p>" }
POST /v1/novasynth/scenarios/generate   { "systemPrompt": "<agent prompt>", "count": 3, "instructions": "...", "projectId": "<p>" }
→ { jobId, status: "pending" }
→ poll GET /v1/novasynth/generation-jobs/:id   (status: pending|running|completed|failed|cancelled)
   completed job carries generated personas[] / scenarios[]
```

Or create hand-authored ones directly (synchronous):
```
POST /v1/novasynth/personas   { "name": "...", "description": "...", "goal": "...",   // + personalityTraits[], primaryLanguage[], tonePreference, voice fields ...
POST /v1/novasynth/scenarios  { "name": "...", "description": "...", "events": [ {"id","parent_id","action","condition"} ], "scenarioType": "conversation" }
```
Scenario `events` form a tree (`parent_id` null = root); `action` is caller **intent only**,
`condition` is a backward-looking "already-said" prerequisite. `scenarioType`:
`conversation | workflow | red_team | knowledge_base | edge_case`.

**Before running, validate.** Generated scenarios are often subtly wrong (unreachable
events, intent that doesn't match the tag, gaps in coverage). Run the checks in
`novasynth-audit.md` (job 1) and fix/fill before spending call credits — do **not** run a
batch on unvalidated scenarios.

## 3S-c. Trigger the batch run

`projectId` is **required** (query or body). Identify the agent via `endpointId`, and pair
personas × scenarios one of two ways (mutually exclusive):

```
POST /v1/novasynth/batch-runs
{ "name": "...", "projectId": "<p>", "endpointId": "<endpoint>",
  // EITHER explicit pairs (≤1000, no dups):
  "pairs": [ { "personaId": "...", "scenarioId": "..." } ],
  // OR full matrix / cross-product (product ≤1000):
  "personaIds": ["..."], "scenarioIds": ["..."],
  "mode": "voice",                 // voice | text
  "concurrencyLimit": 1,           // 1–20 (default 1 = sequential)
  "maxCallDurationS": 300,         // 60–600; the per-call wall-clock cap
  "callDelayMs": 2000, "retryFailedRuns": false }
→ { batchRun: { id, totalRuns, runIds[] } }
```

**Pairing discipline (don't cross-product blindly):** pick the personas that *fit* each
scenario — the top ~2 apt personas per scenario — and skip persona×scenario combos that
contradict each other. A full matrix wastes credits on nonsensical pairs. `novasynth-audit.md`
covers why.

**Note `maxCallDurationS`:** every call is hard-cut at this wall-clock cap (default 300s /
5 min). A call cut at the cap is a *harness* cutoff, not the agent hanging up — don't let
the audit misread it as an agent defect.

## 3S-d. Poll to completion

```
GET /v1/novasynth/batch-runs/:id?projectId=<p>     (poll; batchRun.status + runSummary)
```
Batch terminal: `completed | failed | cancelled | partial_failure`. Per run:
`GET /v1/novasynth/runs/:id?projectId=<p>` (**projectId required**) → `run` with
`status`, `traceId`, `audioUuid`, `turnCount`, `transcriptNormalized`, `datasetItemId`,
`error`. A run with `status:failed` / `turnCount:0` / `traceId:null` is an **infra failure**
(endpoint auth, audio init, timeout) — re-run it, don't score it as a bot fault.

## 3S-e. Scores + dataset

NovaSynth auto-analyzes each run: it posts the transcript to a dataset item and runs an
eval, producing per-run scorer results.

```
python scripts/fetch_to_file.py "/v1/novasynth/batch-analysis/<batchRunId>" --out /tmp/analysis.json
```
Envelope `{ statusCounts, analyses[] }`; each `analyses[]` row is one run's
`SyntheticRunAnalysis` — `runId`, `status` (`pending|building_item|posted_to_dataset|eval_running|completed|failed`),
`score`, `passed`, **`scorerResults` (Json)**, `datasetSlug`, `datasetItemId`, `evalJobId`.
(`POST /v1/novasynth/batch-analysis/:batchRunId/rebuild` re-runs analysis.) The `datasetSlug`
here is the scored dataset — from this point the **normal journey resumes**: audit the calls
+ scorers (`novasynth-audit.md`), then diagnose with NovaPilot (`diagnose-novapilot.md`) on
that `datasetSlug`.

## 3S-f. (Optional) NovaSynth report

For a per-call PDF (transcripts + scorer tables + key observations) straight from the batch:

```
POST /v1/novasynth/batch-runs/:id/report?projectId=<p>
{ }   # omit body to auto-derive columns from the scorers that ran, or supply:
{ "categories": { "<column title>": ["<scorer id>", ...] },
  "failureGateCategoryTitle": "Affects Call Success" }   # this category's scorers gate pass/fail
→ { report: { id, status } } ;  poll GET /v1/novasynth/batch-runs/:id/report  (pending|generating|completed|failed)
→ completed → signed PDF URL ;  POST .../report/send-email { "scope": "me" } to email it
```
`categories` maps report columns → ordered scorer ids; the category named exactly
**`Affects Call Success`** defines which scorers decide call success. This platform report is
the right choice for a single clean batch; for coalescing multiple batches, custom scorers,
or edits, drive it from the local `novaeval` package instead (see the `novasynth-run` skill
in `claude-skills/`).
