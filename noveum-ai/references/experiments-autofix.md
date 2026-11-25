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
  "reviewPlan": true,          // default: draft a plan first, spend nothing on replays
  "timeLimitMinutes": 120,     // optional: 90 | 120 | 180 | 240; the preset sets the default
  "experiments": [...] }       // optional, review first only: your own changes (step 3)
→ 201 { "run": { "id": "<runId>", "status": "queued", ... } }
```

The source report must be `completed`. AutoFix replays exactly the conversations that
report analyzed, so a 409 asking you to run NovaPilot again means the report predates
that record: run NovaPilot again and start from the new report.

Credits are held when the worker starts and settled to measured spend at the end; a 429
means the wallet cannot cover the hold. There are two holds:

| Hold | When | quick | balanced | thorough |
|---|---|---|---|---|
| Plan | review-first run starts drafting | 1,000 | 1,000 | 1,000 |
| Test | `/start` on a reviewed plan, or a test-now run starts | 2,000 | 4,000 | 7,000 |

`run.authorizedCredits` is the sum of the holds the run takes (plan plus test for review
first, test only for test now): the most it can ever spend, Continue included. State the
preset and both holds, and get the user's go-ahead before starting. A longer
`timeLimitMinutes` gives the search more time; it never changes the holds.

## 2. Poll

```
GET /v1/autofix/runs?projectId=<project>&sourceReportId=<reportId>&limit=5   (10s)
→ { runs: [{ id, status, progress, creditsUsed, ... }], total, limit, offset }
```

Statuses: `queued`, `planning`, `awaiting_review`, `processing`, then `completed`,
`failed` or `cancelled`. While the run works, `progress` has the `phase` (`loading`,
`analyzing`, `authoring`, `backtesting`, `validating`, `tool_fixes`, `combining`,
`reporting`), `currentRec` (the issue being worked on), `recsDone` of `recsTotal`, the
improvement cycle `generation` of `generationsMax`, and spend against the budget. Tell the
user spend in credits, never dollars; `creditsUsed` is what the run charged. Poll the list,
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
save and start. Starting is a separate spend: `/start` takes the test hold on top of the
plan hold already taken. Quote it and wait for a yes before you call `/start`, for
example: "Testing this plan holds 4,000 credits on top of the 1,000 the draft held, so
the run can spend at most 5,000. Start testing?" A 429 from `/start` means the wallet
cannot cover the test hold.

```
PUT  /v1/autofix/runs/<runId>/plan    { "projectId": "<project>", "plan": [...] }
POST /v1/autofix/runs/<runId>/start   { "projectId": "<project>" }
```

The API rejects a plan with duplicate ids, with nothing switched on, or with an enabled
variant whose `parentId` is switched off; switch variants off with their parent. A
`search` must be copied character for character from the live prompt, or it changes
nothing.

To test a change of your own, add it to a review-first run while AutoFix drafts the plan
or while the plan waits for review:

```
POST /v1/autofix/runs/<runId>/experiments
{ "projectId": "<project>",
  "experiment": { "type": "tool.schemaEdit", "sourceRecId": "<issue recId>",
                  "toolName": "<recorded tool>", "label": "Look the policy up first",
                  "patch": { "required_add": ["policy_id"] } } }
→ 201 { "experiment": { "id": "user_...", "origin": "user", "run": true, ... },
        "placement": "plan", "status": "awaiting_review" }   // "pending" while drafting
```

The experiment takes the same three shapes as a plan entry, without `id`, `run` or
`origin`. `sourceRecId` names the report issue it fixes: the `recId` of a `planIssues`
entry, or the `sourceRecId` of a drafted entry for that issue. Before the plan is drafted,
use the report recommendation's `id`, or `cand_<n>` for the n-th issue of a report whose
recommendations carry none. A `search` must appear in
the agent's recorded prompt and `toolName` must be a tool the recorded conversations list;
only `description` can change on a tool recorded without a typed parameter schema.
Otherwise the API answers 400 and names the valid choices. While the plan waits for review
the change is appended to it, switched on; while AutoFix still drafts it, the change is
kept and joins the plan once drafted. Other runs, and runs that skip review, answer 409.

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
  `rule` or `toolChange`. A `tool-schema` fix changes the tool definition the agent
  registers, not its prompt. `toolChange` lists one edit per line: `Tool: <name>`,
  `New description: <text>`, `Now required: <names>`, `No longer required: <names>` and
  `Parameter <name>: <JSON schema>`. Step 7 applies it with "Apply a tool-schema fix" in
  `apply-fixes.md`.
- `metrics[]` per check (before, after, delta, readout), `detectedBy[]` (failing checks and
  fail rates), `evidence[]` (item ids with notes), `nextStep`.

Start the summary from `run.report.selection`: `selected[]` are the fixes that worked
(`recId`, `kind`, `tier`, `combined`, `reason`; a `validated` tier is proven, a
`strong-evidence` tier is promising and never proven), and `rejected[]` the ones dropped,
with `outcome` and `reason`. Every selected fix has passed a ship review of its diff against the current prompt and the issue. An outcome of `review_needed` means that review failed or could not run; `shipReview.problems` lists why (`contradicts_existing_rule`, `weakens_security_or_disclosure`, `duplicates_existing_section`, `placeholder_or_canned_answer`, `off_issue`, `quotes_conversation_content`). Never ship such a fix without a person reading the change. An outcome of `regressed` means the held-out test found a clear
drop on the checks in `harmedScorers`: never ship it. `run.report.budget.perRec[]` shows per
fix how many improvement cycles ran (`generationsRun`; with a budget the engine decides how
many, and `generationsMax` is only a safety ceiling) and why the cycles ended
(`stopReason`). Why each issue stopped, and what to do about it, is in section 5. Plan
entries the engine already knows it cannot measure carry `untestable` with a reason
(`too_few_items`, `scorer_not_backtestable`, `multi_turn_scorer`); they are skipped, so do
not offer to turn them on. `run.report.meta`
says which model the replays ran on (`replayModel`, `replayModelSource` is `fallback` when the
dataset did not record the agent's model).

`run.report.experiments[]` lists every change tried with its held-out outcome
(`win`, `regression`, `no change`), and `run.report.backtestDiagnostics` the totals.
`run.markdown` is the full written report.

## 5. Why each issue stopped, and what to do next

Every entry of `run.report.recommendations[]` carries `stop: { reason, detail }`, where
`detail` is a short sentence or null. Act on each issue's own `stop.reason`, never on a
run-wide flag such as `run.report.budget.exhausted`:

| `stop.reason` | What happened | What to do |
|---|---|---|
| `won` | a fix was validated | decide it (section 6) |
| `no_win` | fully tested; nothing beat the current prompt (harmful, trade-off or no effect) | rework the fix or try another experiment (section 3) |
| `deadline` | the time limit stopped this issue before it finished | Continue with the existing authorization |
| `budget` | the credit cap stopped this issue before it finished | ask before a higher cap |
| `no_data` | too few matching conversations to test or certify | ask for more matching traffic |
| `untestable` | single-turn replay cannot measure this change | multi-turn simulation or a live A/B test |
| `skipped` | the user left it out of the plan | nothing, unless they want it in a new run |

A run with no validated fix still has a report: its issues, their stop reasons and how
many were tested. Offer the PDF (section 7) whenever `run.report` exists, so the user can
share why nothing shipped. Never invent a fix to fill it.

**Deadline: continue, no new hold.** `GET /v1/autofix/runs/<runId>` returns `canContinue`
and `continueCreditsLeft` (`authorizedCredits` minus `creditsUsed`). When `canContinue` is
true:

```
POST /v1/autofix/runs/<runId>/continue
{ "projectId": "<project>", "timeLimitMinutes": 180 }   // optional, 90 | 120 | 180 | 240
→ 200 { "run": { "status": "queued", ... }, "started": true }
```

Continue reruns no finished test. It resumes only the issues the deadline stopped and spends
at most `continueCreditsLeft`, the rest of the cap the user already approved, so it holds
nothing new. Still say so and confirm before calling it. A second call while the run is
queued or working returns the same run with `started: false` and starts nothing. When
`canContinue` is false (the run is still working, no issue stopped on the deadline, or no
credits are left), Continue answers 409 with the reason in plain words: pass it on, and
when credits are the limit treat the issues as `budget`.

Example: `run.authorizedCredits` 5,000, `creditsUsed` 3,150, `canContinue` true,
`continueCreditsLeft` 1,850, and two issues with `stop.reason: "deadline"`. Say: "The time
limit stopped two of the five issues before they finished. Continue picks up only those two
and can spend at most the 1,850 credits left of the 5,000 you approved; nothing new is held.
Continue with a 180-minute limit?" On a yes, POST `/continue`, then poll as in section 2.

**Budget: ask before a higher cap.** Continue cannot add credits. Example: a balanced
review-first run, `creditsUsed` 4,980 of `authorizedCredits` 5,000, and one issue with
`stop.reason: "budget"`. Say: "The 5,000-credit cap ran out before the refund-policy issue
finished testing. A new thorough run from the same report holds 1,000 credits to draft the
plan and 7,000 to test it. Start one?" Start nothing until the user says yes, and quote the
test hold again before its `/start`.

**No data: ask for more matching traffic.** More credits or more time do not help. Example:
the income-question issue has `stop.reason: "no_data"` and `detail` "Only 4 recorded
conversations ask about income." Say: "AutoFix could not test the income question: only 4
recorded conversations ask about it. Once more of that traffic is recorded, run NovaPilot
on it and start AutoFix from the new report." The issue's
`detectedBy[]` and `evidence[]` show what a matching conversation looks like; NovaSynth
(`novasynth-generate-run.md`) can generate test traffic when production traffic is scarce.

## 6. Record decisions

```
PUT /v1/autofix/runs/<runId>/decisions
{ "projectId": "<project>", "recommendationId": "<key>", "decision": "adopt", "note": "..." }
// adopt | reject | clear; returns { decisions: [...] } for the whole run
```

Decisions are per issue and are only accepted on completed runs. `adopt` keeps the fix
whose `key` you send and clears the decision on the issue's other fixes; `reject` rejects
every fix of the issue and `clear` removes the issue's decisions (send any fix `key` of
the issue for both). The change is applied in one transaction, so an issue is never left
half decided. A key that is not in the run's report returns 404.

## 7. Share the report

```
GET  /v1/autofix/runs/<runId>/pdf?projectId=<project>&locale=en      → application/pdf
POST /v1/autofix/runs/<runId>/send-email { "projectId": "<project>", "scope": "me" }   // me | team
→ { sent, failed }
```

Both answer 409 until the run has a report and 422 when the stored report cannot be read.

Both are rate limited per organization: the PDF route allows 10 downloads a minute and the
email route 5 sends every 10 minutes. Over the limit they answer 429 with a `Retry-After`
header. Unlike the 429 in section 1, this is not about the wallet: wait that many seconds and
try again, and tell the user why.

## Which fixes to carry into step 7

Only (a) `validated` fixes, (b) `strong-evidence` fixes the user explicitly accepts after
hearing they are not yet proven, and (c) NovaPilot recommendations the user accepts without
a backtest, labelled as such in the PR. Never carry a fix the backtest flagged as a
regression. A `tool-schema` fix goes to the tool's registered definition, not the prompt. Proven means higher scores from the customer's own checks on replayed
conversations, not confirmed business impact: say so, and suggest a live A/B test for
anything business critical. To confirm a shipped fix, run NovaPilot and a new AutoFix run
on traffic recorded after the change and compare.
