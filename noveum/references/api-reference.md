# API reference essentials

Base URL: `https://api.noveum.ai/api` (self-hosted deployments override; the SDK env var is
`NOVEUM_ENDPOINT`). Every request: `Authorization: Bearer $NOVEUM_API_KEY`. The key is
org-scoped — the org is inferred from it; do not pass org headers with API-key auth.

Authoritative schemas: the MCP server's tools (generated from the live OpenAPI spec) or
`https://noveum.ai/docs`. This file covers what an agent needs constantly.

## Ingest contract (what the SDK sends — also usable directly)

```
POST /v1/traces          body: { "traces": [ <Trace>, ... ] }   (max 1000/request)
POST /v1/traces/single   body: <Trace>
```

Minimal valid Trace:

```json
{ "name": "chat-request", "project": "<project>", "environment": "production",
  "start_time": "2026-07-16T00:00:00Z", "end_time": "2026-07-16T00:00:01Z",
  "duration_ms": 1000, "status": "ok", "span_count": 1,
  "sdk": { "name": "noveum-trace", "version": "1.x" },
  "spans": [ { "span_id": "s1", "trace_id": "t1", "name": "llm.call",
      "start_time": "2026-07-16T00:00:00Z", "end_time": "2026-07-16T00:00:01Z",
      "duration_ms": 1000, "status": "ok",
      "attributes": { "llm.model": "gpt-4o", "llm.provider": "openai",
                      "llm.input_tokens": 12, "llm.output_tokens": 30,
                      "llm.input.messages": "[...]", "llm.output.response": "..." } } ] }
```

Notes: the format is Noveum's own JSON (not OTLP). `project` auto-creates the project.
Ingest is async (returns job ids) — confirmation = querying the trace back, not the 2xx.

## Query traces

```
GET /v1/traces?project=<p>&limit=20&include_spans=true
      &status=error&service_version=<v>&sort=start_time:desc&offset=0
GET /v1/traces/:id
GET /v1/traces/:traceId/spans
GET /v1/traces/filter-values        // all facet values incl. serviceVersions
GET /v1/traces/connection-status    // has this org ever connected telemetry
```

## Polling contract (memorize this)

Heavy work runs in background workers. After a kickoff POST returns an id, poll the
matching GET until a terminal status. Never call queued work "done".

| Work | Poll | Cadence | Terminal |
|---|---|---|---|
| ETL run | `GET /v1/etl-jobs/:id/runs` | 3s active / 15s idle | completed·failed·cancelled |
| Mapper codegen | `GET /v1/etl-jobs/:id/novaeval/:runId` | 2s (cap ~5m) | completed·failed·cancelled |
| Recommend scorers | `GET /v1/eval-jobs/recommend-scorers/:jobId` | 3s (cap ~5m) | completed·failed·cancelled |
| Eval run | `GET /v1/eval-jobs/:id/runs/:runId` | 3s active / 15s idle | completed·failed·cancelled |
| NovaPilot | `GET /v1/novapilot/reports/:reportId` | 5s | completed·failed |

## Credits & quotas (say the number before spending)

- Eval: 1 credit × items × premium(LLM-judge) scorers; rule-based scorers free; if any
  premium scorers are used, minimum 5 (else 400 `MIN_PREMIUM_SCORERS_REQUIRED`).
- NovaPilot: per analyzed item (preview count via `POST /v1/novapilot/filter-preview`).
- Out of credits → 429 `CREDIT_QUOTA_EXCEEDED` (with `Retry-After`). Stop; tell the user.
  Buying credits is a human/dashboard action — never attempt it.
- Usage snapshot: `GET /v1/status`.

## Common errors

| Code | Meaning | Action |
|---|---|---|
| 401 | Bad/expired key | Ask the user for a valid key; never invent one |
| 403 `ORG_CONTEXT_MISMATCH` | Org header conflicts with the key's org | Drop the org override |
| 400 validation | Payload mismatch | Re-check against the live OpenAPI/MCP schema |
| 429 (rate limit vs credit) | Read the error code | Backoff vs stop-and-report |

## What this key CANNOT do (by design — don't try)

Create/rotate API keys, manage billing or buy credits, create organizations or manage
members, access another org's data. These are dashboard/human actions.
