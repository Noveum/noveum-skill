# Audit a NovaPilot report before acting on it (step 5, verify)

NovaPilot (`diagnose-novapilot.md`) is a strong diagnostician, but its recommendations are
**claims, not facts** — and some are wrong: the cited items don't actually show the issue,
`affected_scorers` are mis-tagged, or the fix is the wrong altitude (a heavyweight pipeline
change where a one-line prompt tweak would do, or vice versa). **Run this before AutoFix
(`experiments-autofix.md`) or apply-fixes (`apply-fixes.md`)** — verifying first is far
cheaper than backtesting or shipping a recommendation built on a bad attribution.

Base `https://api.noveum.ai/api`, header `Authorization: Bearer $NOVEUM_API_KEY`. Work from
the report already downloaded to disk in `diagnose-novapilot.md`
(`/tmp/report.json`) — never re-fetch it inline. Dataset items + traces + scorer results are
fetched per the `context-safety.md` / `setup-evals.md` patterns.

## What you're auditing

Each recommendation (under `report.analysis.analysis.recommendations{surface}{severity}[]`)
carries `title`, `issue_description`, `action_items`, `affected_scorers`, and `evidence`
(`item_ids`, `trace_ids`). Treat **each recommendation = one issue**, **each `item_id` = one
attributed occurrence**. Run the three phases in order — each phase's survivors feed the next.

## Phase 1 — Item-attribution verification

Fan out **one subagent per `(issue, item_id)` pair** — never batch items, a bad attribution
must be caught individually. Give each subagent the recommendation's specific claim, the full
dataset item (fetched the same shape the platform scored on:
`GET /v1/datasets/:slug/items/:itemId`), and — when the claim needs execution detail — the
trace spans for that item's `traceId`. For claims that hinge on audio signal (tone, pacing,
pronunciation), let it fetch the audio (`GET /v1/audio/:uuid/serve`).

Ask for one verdict: **ATTRIBUTED / NOT ATTRIBUTED / UNVERIFIABLE**, with a one-line
quote-backed reason. **Audio-metric scorers themselves** (`stt_efficacy`, `mos`, `gibberish`,
`tone_clarity`, `pronunciation`, latency-as-artifact) are **out of scope** — the subagent
must say "cannot verify — audio-metric scorer", not adjudicate them.

Aggregate per issue: keep only **ATTRIBUTED** items; drop NOT ATTRIBUTED; list UNVERIFIABLE
separately (not counted as failures). **An issue with zero ATTRIBUTED items → flag for
removal** and skip phases 2–3 for it.

## Phase 2 — Affected-scorer sanity

For each surviving issue, pull the **actual scorer results** for its attributed items (don't
trust the report's claim): do the listed `affected_scorers` really score low/fail there?
Flag scorers listed but not actually low → **spurious**; scorers the issue clearly implicates
but that are missing → **missing**.

## Phase 3 — Fix sanity

For each issue still standing, evaluate `action_items` against the issue + surviving items +
real scorer results:
- **Altitude** — a prompt-level issue given a pipeline-level fix, or vice versa? NovaPilot
  systematically over-engineers; call out where a one-line system-prompt instruction would
  fix what's proposed as a new pipeline stage.
- **Plausibility** — does the fix address the root cause shown in the items, or just the
  symptom in the title?
- **Blast radius** — could it break flows not covered by the attributed items (e.g. banning a
  phrase that one other scenario requires)?

## Report

One table, one row per original recommendation:

| Issue | Items in / kept / dropped | Scorer verdict | Fix verdict | Notes |

Below it: **issues flagged for removal** (0 attributed) with the reason; **unverifiable
items** listed separately; **scorer mismatches** (spurious/missing); **fix concerns**
(altitude, blast radius). Feed the survivors — not the raw report — into
`experiments-autofix.md` or `apply-fixes.md`.
