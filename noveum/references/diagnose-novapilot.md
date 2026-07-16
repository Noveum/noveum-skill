# Diagnose with NovaPilot (step 5)

NovaPilot analyzes a scored dataset and produces a diagnosis report: overall health
score/grade, per-agent findings (it auto-detects multi-agent fleets), prompt issues with
concrete search/replace suggestions, failure patterns, and prioritized recommendations
with measured blast radius.

**Precondition:** the dataset's items must already have scorer results (run step 4 first —
NovaPilot analyzes scores, it does not create them).

## Run

```
POST /v1/novapilot/run
{ "organizationSlug": "<NOVEUM_ORG_SLUG>", "projectId": "<project>",
  "datasetSlug": "<slug>" }
// optional scoping: "datasetItemIds": [...] or "filterConfig": {...}; cap 10,000 items
→ { "reportId": ... }
```

**Credits:** charged per analyzed item (check `POST /v1/novapilot/filter-preview` for the
count first and state the estimate to the user before running).

## Poll — status via the LIST endpoint, never the by-id one

```
GET /v1/novapilot/reports?projectId=<project>&limit=5     (5s)  → summaries incl. status
```
Terminal: `completed | failed`. **Do not poll `GET /reports/:reportId`** — on `completed`
that response inlines the full `analysis` (hundreds of KB) straight into your context.
Once the summary shows `completed`, download the full report to disk and read it
selectively:
`python scripts/fetch_to_file.py "/v1/novapilot/reports/<id>?projectId=<p>" --out /tmp/report.json`
then extract only what you need (e.g.
`python3 -c "import json;a=json.load(open('/tmp/report.json'))['analysis'];print(a['overallHealth']);[print(r['issue_description'][:120]) for r in a['recommendations'][:5]]"`).
See `context-safety.md`.

## Read the report

Key fields in `analysis`:
- `overallHealth { score, grade, summary }`
- `recommendations[]` — each has `issue_description`, `recommended_change`, `justification`,
  `confidence`, affected counts, and — when the fix is a concrete prompt edit —
  verbatim `search` / `replace` strings (character-exact substrings of the live system
  prompt) plus `fixType`.
- `systemPromptAnalysis { currentPrompt, promptIssues[] }` — prompt text reconstructed
  from traces, with per-issue search/replace.
- `failurePatterns[]`, `scorerBreakdown[]`, `agentFleet` (multi-agent detection).

A markdown rendering exists as the MCP resource
`noveum://novapilot-report-markdown?reportId=<id>&projectId=<project>` — but it inlines
the whole report: use it **only via `@noveum/mcp-local`** (which saves it to a file). On
the hosted server, stick to the `fetch_to_file.py` download above.

## What to do with it

1. Present the top findings (health, top 3-5 recommendations with blast radius).
2. For each concrete recommendation, the next step is **not** to apply it blindly:
   - If AutoFix/experiments are available on the org → validate first
     (`experiments-autofix.md`).
   - Otherwise → apply with the user's review (`apply-fixes.md`), clearly labeled as
     unvalidated.
3. Recurring diagnosis: `POST /v1/novapilot/schedules` sets up cron-based re-runs with
   email reports (`{ projectId, name, datasetSlug, cronExpression, timezone, enabled }`).
