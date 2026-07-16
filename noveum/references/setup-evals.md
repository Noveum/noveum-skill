# Set up datasets and evaluations (steps 3–4)

All endpoints: base `https://api.noveum.ai/api`, header `Authorization: Bearer $NOVEUM_API_KEY`.
Prefer the MCP tools if connected (`connect-mcp.md`) — they mirror these routes exactly.
Poll cadences and terminal statuses: `api-reference.md`.

## 3a. Create a dataset

```
POST /v1/datasets
{ "name": "<human name>", "dataset_type": "conversational",   // or "agent" | "g-eval" | "custom"
  "environment": "production", "project_id": "<project>" }
```
Note the returned `slug` — everything below is slug-addressed.

## 3b. Create an ETL job (traces → dataset items)

```
POST /v1/etl-jobs
{ "name": "...", "projectId": "<project>", "datasetSlug": "<slug>",
  "environment": "production", "isConfigurationDone": false }
```

The ETL job needs Python `mapperCode` that transforms traces into dataset items. Generate
it with the AI mapper:

```
POST /v1/etl-jobs/:id/novaeval/transformation-code-gen   { "traceIds": ["<5-10 representative trace ids>"] }
→ poll GET /v1/etl-jobs/:id/novaeval/:jobRunId  (2s, cap ~5min)
```

**Gotcha (will silently no-op if skipped):** the generated `outputCode` is NOT auto-applied.
Persist it explicitly:

```
POST /v1/etl-jobs/:id/versions   { "code": "<outputCode>", "source": "ai_generated" }
```

Optional sanity checks before the full run:
- `POST /v1/etl-jobs/run-mapper { "mapperCode": ..., "traceId": ... }` — smoke-test one trace
- `POST /v1/etl-jobs/:id/trace-filter-preview { "filterConfig": ..., "skipProcessed": true }` — count what will be processed

## 3c. Run the ETL

```
POST /v1/etl-jobs/:id/trigger
{ "filterConfig": { ... }  // or "traceIds": [...]; one of the two is required
, "skipProcessed": true }
→ poll GET /v1/etl-jobs/:id/runs   (3s while active)
```

Acceptance: run status `completed` and `datasetItemsCreated > 0`. Inspect a few items
(`GET /v1/datasets/:slug/items?fullContent=true` — without `fullContent=true` the list view
truncates long fields to placeholders; never QA content from the truncated view).

## 4a. Pick scorers

Get recommendations, then map them to configs yourself (recommendations are advisory —
nothing auto-applies them):

```
POST /v1/eval-jobs/recommend-scorers   { "datasetSlug": "<slug>" }
→ poll GET /v1/eval-jobs/recommend-scorers/:jobId   (3s, cap ~5min)
→ results.scorers_recommended[]: { scorer_name, reasoning, confidence, priority }
```

Cross-reference names against the catalog (`GET /v1/scorers`) to get `scorerId`/`scorerType`.
Present the recommended set + reasoning to the user before spending credits.

## 4b. Create and trigger the eval job

```
POST /v1/eval-jobs
{ "name": "...", "datasetId": "<id>", "datasetSlug": "<slug>",
  "datasetType": "conversational",             // must match how items were shaped
  "projectId": "<project>",
  "scorerConfigs": [ { "scorerId": "...", "scorerType": "...", "scorerName": "...",
                       "threshold": 0.7 } ],
  "isEnabled": true }

POST /v1/eval-jobs/:id/trigger
{ "skipEvaluated": true }        // add datasetItemIds or filterConfig to scope; neither = full dataset
→ poll GET /v1/eval-jobs/:id/runs/:runId   (3s while active)
```

**Credits (state this before triggering):** LLM-judge ("premium") scorers cost
1 credit × items × premium-scorer-count; rule-based scorers are free. If any premium
scorers are used, at least 5 are required (`MIN_PREMIUM_SCORERS_REQUIRED` otherwise).
A 429 `CREDIT_QUOTA_EXCEEDED` means the org is out of credits — stop and tell the user.

## 4c. Read results

```
GET /v1/eval-jobs/:id/results?runId=<runId>
```
Per-scorer aggregates (avg/min/max/percentiles, passedCount) + per-item
`{ itemId, score, passed, reasoning, sourceTraceId }`. Summarize: worst scorers, failure
rate, 2-3 example failures with reasoning. Then proceed to `diagnose-novapilot.md`.
