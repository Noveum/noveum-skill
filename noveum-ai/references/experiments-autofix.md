# Validate fixes with AutoFix (step 6)

> **Availability:** AutoFix needs NovaPilot on the organization's plan. If the
> `/v1/autofix/*` routes return 403 or 404, skip to `apply-fixes.md` and label fixes
> "diagnosed, not backtested". Do not fake validation.

AutoFix takes a completed NovaPilot report and **backtests** its recommendations. It turns
each one into concrete prompt or tool-schema changes, replays the conversations the
recommendation claims to fix on the customer's own model with and without each change,
re-scores both with the same eval scorers, evolves the best candidates, and checks the
winner on held-out conversations it never tuned on. The output is fixes with evidence, not
suggestions.

Every route takes `?organizationSlug=<org>`; bodies carry `projectId`.

## 1. Start a run

```
POST /v1/autofix/runs
{ "projectId": "<project>", "sourceReportId": "<novapilot reportId>",
  "preset": "balanced",        // quick | balanced | thorough
  "reviewPlan": true }         // default: draft a plan first, spend nothing on replays
→ 201 { "run": { "id": "<runId>", "status": "queued", ... } }
```

The source report must be `completed`. AutoFix replays exactly the conversations that
report analyzed, so a 409 asking you to run NovaPilot again means the report predates
that record: run NovaPilot again and start from the new report. Credits are held when the worker starts and
settled to measured spend at the end; a 429 means the wallet cannot cover the hold. State
the preset and get the user's go-ahead before starting.

## 2. Poll

```
GET /v1/autofix/runs?projectId=<project>&sourceReportId=<reportId>&limit=5   (10s)
→ { runs: [{ id, status, progress, creditsUsed, ... }], total, limit, offset }
```

Statuses: `queued`, `planning`, `awaiting_review`, `processing`, then `completed`,
`failed` or `cancelled`. `progress` counts recommendations backtested, candidates tried,
validated fixes, clean wins, trade-offs and regressions while the run works. Poll the list,
never the by-id route, until the status is terminal or `awaiting_review`.

## 3. Review the plan (when `reviewPlan` is true)

At `awaiting_review` the run holds a plan: one entry per change AutoFix will test.

```
GET /v1/autofix/runs/<runId>?projectId=<project>      → { run: { plan: [...] } }
```

Each entry is one of three types, all with `id`, `run`, `label`, `origin`, `parentId`,
`sourceRecId`, `agentName` and `affectedScorers`:

```json
{ "type": "prompt.searchReplace", "edit": { "search": "<verbatim prompt text>", "replace": "<new text>" } }
{ "type": "prompt.append", "replace": "<rule appended to the prompt>" }
{ "type": "tool.schemaEdit", "toolName": "<tool>", "patch": { "description": "...", "required_add": ["..."] } }
```

Show the user the plan, switch off (`run: false`) anything they would never ship, then
save and start:

```
PUT  /v1/autofix/runs/<runId>/plan    { "projectId": "<project>", "plan": [...] }
POST /v1/autofix/runs/<runId>/start   { "projectId": "<project>" }
```

The API rejects a plan with duplicate ids, with nothing switched on, or with an enabled
variant whose `parentId` is switched off; switch variants off with their parent. A
`search` must be copied character for character from the live prompt, or it changes
nothing.

`POST /v1/autofix/runs/<runId>/cancel { "projectId": "<project>" }` stops a run at its
next checkpoint; spend so far is charged.

## 4. Read the report

The completed run is large. Stream it to disk and read it selectively (see
`context-safety.md`):

```
python scripts/fetch_to_file.py "/v1/autofix/runs/<runId>?projectId=<project>" --out /tmp/autofix.json
```

`run.report.recommendations[]` holds one entry per fix AutoFix tried. Several fixes can
share a NovaPilot issue (same `title` and `agentName`), for example a prompt edit and a
tool-schema change; each has its own unique `key`. Per fix:

- `confidenceTier`: `validated` (proven: target checks improved on held-out conversations
  and nothing else got clearly worse), `confirmed-defect` (the recorded calls prove the
  defect; fix it in code or a schema), `strong-evidence` (promising, needs a bigger test),
  `insufficient-data`, `diagnosed` (not tested yet), `tested-no-effect`, `infra` (not a
  prompt problem).
- `band`: the measured effect range on held-out conversations; `excludesZero` false means
  not conclusive yet.
- `diff`: `kind` (`search-replace`, `append-rule`, `tool-schema`) with `search`, `replace`,
  `rule` or `toolChange`.
- `metrics[]` per check (before, after, delta, readout), `detectedBy[]` (failing checks and
  fail rates), `evidence[]` (item ids with notes), `nextStep`.

`run.report.experiments[]` lists every change tried with its held-out outcome
(`win`, `regression`, `no change`), and `run.report.backtestDiagnostics` the totals.
`run.markdown` is the full written report.

## 5. Record decisions

```
PUT /v1/autofix/runs/<runId>/recommendations/<key>
{ "projectId": "<project>", "decision": "adopted" }    // adopted | rejected | null clears it
```

Decisions are per fix `key`, are visible in the app, and are only accepted on completed
runs. A key that is not in the run's report returns 404.

## Which fixes to carry into step 7

Only (a) `validated` fixes, (b) `strong-evidence` fixes the user explicitly accepts after
hearing they are not yet proven, and (c) NovaPilot recommendations the user accepts without
a backtest, labelled as such in the PR. Never carry a fix the backtest flagged as a
regression. Proven means higher scores from the customer's own checks on replayed
conversations, not confirmed business impact: say so, and suggest a live A/B test for
anything business critical. To confirm a shipped fix, run NovaPilot and a new AutoFix run
on traffic recorded after the change and compare.
