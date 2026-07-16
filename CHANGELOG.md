# Changelog

## 0.3.0 — 2026-07-16

Context safety + full live E2E dogfood (all 7 steps run against production by an agent
following the skill literally; 0 credits spent; 25 claims verified, 7 corrected).

- **New `references/context-safety.md`** — the large-response discipline: count before
  fetching, stream big payloads to disk, mcp-local preference, per-item `fullContent`,
  reports downloaded once; with live-measured sizes (10 traces w/ spans = 171 KB, one
  49-span trace = 145 KB, scorer catalog = 169 KB).
- **New `scripts/fetch_to_file.py`** — stdlib streamer: any GET endpoint → file, prints
  only `{savedTo, bytes, sha256}` + 400-char head.
- SKILL.md: context-safety global rule; setup-evals/diagnose-novapilot route large pulls
  through the script.
- **Live-verified corrections:** dataset list truncation is silent/mid-string with no
  marker (and some fields are never truncated — the list view is not size-bounded);
  direct item insertion documented (`{items:[...]}` → `{created}`, no ids returned;
  set `agent_response` or rule-based scorers return -1 "cannot evaluate", which skews
  aggregates while `errorCount` stays 0); eval trigger response IS the run object;
  per-item results shape fixed (`sourceTraceId` absent for direct items); traces
  pagination envelope + `{success, data}` single-trace envelope; ClickHouse vs ISO
  timestamp formats; premium-scorer discriminator = `config.evaluationType`.

## 0.2.0 — 2026-07-16

Live-validated against the production API, plus connection guide and diagrams.

- **Fixed (would have broken verification):** `check_integration.py` now uses the live
  trace-query parameters (`size`/`from`/`includeSpans` — camelCase), and treats the SDK's
  literal `service_version: "unknown"` as unset.
- New `references/getting-connected.md`: accounts/keys, REST Bearer auth, **MCP over
  OAuth 2.1 (URL-only clients)** and **MCP with an API-key header (headless)**, decision
  diagram, org binding, scopes, connection verification via `GET /v1/status`
  (absorbs the former `connect-mcp.md`).
- SKILL.md: explicit "Step 0 — connect" with a status-check acceptance, journey
  flowchart; README: environment/data-flow and journey diagrams (Mermaid).
- api-reference.md: live-validated query params, response envelope, and `/v1/status`
  shape; documented the camelCase-query vs snake_case-payload asymmetry.

## 0.1.0 — 2026-07-16

Initial release.

- `noveum` skill: 7-step journey (integrate → verify → dataset → evals → NovaPilot →
  experiments → apply fixes), each step gated on a platform-side acceptance check.
- Integration references for LangChain/LangGraph, CrewAI, LiveKit, Pipecat, and manual
  (direct provider SDK) apps — attribute vocabulary validated against production
  integrations.
- `scripts/send_test_trace.py` and `scripts/check_integration.py` (stdlib-only)
  connectivity + trace-completeness verification.
- MCP connection guide covering OAuth 2.1 URL-only flow and Bearer API-key mode.
