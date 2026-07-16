# Changelog

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
