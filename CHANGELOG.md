# Changelog

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
