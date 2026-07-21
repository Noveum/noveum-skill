# Changelog

## 0.6.0 — 2026-07-21

Added the **NovaSynth synthetic-traffic branch** to the journey — generate test traffic when
there's little/no production data, or for targeted adversarial coverage — plus a report-audit
step. All platform-first (`/api/v1/novasynth/...`), grounded in the live API.

- **New `references/novasynth-generate-run.md`** — step 3 synthetic branch: register the
  agent-under-test endpoint, generate/create personas + scenarios (async → poll
  `generation-jobs`), trigger a batch run (`endpointId` + `pairs`/matrix, `maxCallDurationS`
  cap), poll to terminal, pull scores from `batch-analysis`, and optionally render the
  NovaSynth PDF report (`Affects Call Success` gate). Feeds steps 4–5 like real traffic.
- **New `references/novasynth-audit.md`** — validate scenarios before spending call credits
  (schema/reachability/intent/coverage), then audit each call (one subagent per run) + the
  scorer verdicts, carrying the scorer false-pass/false-fail cheatsheet (LLM judges
  under-penalize hard gates; `item_summary`/audio `-1` are infra, not bot faults).
- **New `references/novapilot-audit.md`** — step 5 verify: audit a NovaPilot report's item
  attributions, affected scorers, and fix altitude before AutoFix/apply. One subagent per
  `(issue, item_id)` pair; drop issues with zero attributed items.
- **`SKILL.md`** — journey checklist + references list wired for the synthetic branch (step 3)
  and report audit (step 5).
- **New `claude-skills/`** — the standalone à-la-carte versions of these skills (+
  `noveum-dataset`, and the internal-only `novaeval-scorer`), for use outside the full journey.

## 0.5.0 — 2026-07-16

Renamed the skill `noveum` → `noveum-ai` (ClawHub listing `@noveum-ai/noveum-ai`).

- Folder `noveum/` → `noveum-ai/`; frontmatter `name: noveum-ai` (this is also the
  Claude Code invocation name). Publish workflow `skill_path`, CI validation paths, and
  all install commands updated to match. Install is now `clawhub install noveum-ai` /
  vendor into `.claude/skills/noveum-ai`.
- Description tightened to ≤500 chars (ClawHub short-summary limit) while keeping trigger
  keywords; added a "Learn more" links block (noveum.ai, docs, MCP reference, repo, SDK)
  so the listing explains what the skill does.

## 0.4.0 — 2026-07-16

Published to ClawHub with GitHub auto-sync.

- **ClawHub metadata** in `SKILL.md` frontmatter (`metadata.openclaw`): `emoji`,
  `homepage`, `primaryEnv`, `requires.env`, and per-variable `envVars` descriptions
  (`NOVEUM_API_KEY` required; `NOVEUM_ORG_SLUG`/`NOVEUM_PROJECT`/`NOVEUM_ENDPOINT`
  optional). Added top-level `version` + `homepage`. Description expanded with discovery
  keywords (AI reliability, QA, voice, LangGraph, AutoFix) — still Claude Code compatible.
- **Auto-sync workflow** `.github/workflows/clawhub-publish.yml`: publishing a GitHub
  Release republishes to ClawHub under `@noveum-ai` via the official
  `openclaw/clawhub/.github/workflows/skill-publish.yml@v0.23.1` reusable workflow
  (`skill_path: noveum`); manual runs default to a dry-run.
- README: ClawHub install + publishing section; framed as Noveum's AI Reliability & QA
  Engineer.

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
