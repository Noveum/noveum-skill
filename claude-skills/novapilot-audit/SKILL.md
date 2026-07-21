---
name: novapilot-audit
description: "Audit a NovaPilot report JSON — verify each recommendation's cited issue is actually present in its attributed items, that the affected scorers genuinely score low there, and that the recommended fix is sensible (right altitude: prompt vs pipeline, and unlikely to cause regressions elsewhere). Use when the user asks to audit/validate/sanity-check a NovaPilot report, or check whether a report's recommendations/item attributions/fixes are trustworthy."
trigger: /novapilot-audit
---

# NovaPilot report audit

A NovaPilot report's recommendations make claims that are frequently wrong: items don't actually show the cited issue, affected scorers are mis-tagged, or the fix is the wrong altitude (a heavyweight pipeline change where a one-line prompt tweak would do, or vice versa). This skill verifies each recommendation against ground truth instead of trusting the report at face value.

## Usage

```
/novapilot-audit <path/to/report.json>
```

## Report shape (as produced by NovaPilot)

Recommendations live under `report.analysis.analysis.recommendations` as a **bucket tree** —
`{systemPrompt, tool, other} × {critical, high, medium, low}`. Each recommendation:

```text
{ title, description, category, priority, confidence,
  action_items[]                        # the recommended fix, as a list of steps
  affected_scorers[]                    # scorer names claimed to be impacted
  evidence: { item_ids[], trace_ids[] } # attributed occurrences
}
```

Each recommendation = one "issue." Each `item_id` = one attributed occurrence. (NovaPilot may
instead emit a **flat** `recommendations[]` array with camelCase keys — `actionItems`,
`affectedScorers`, `itemIds`/`traceIds`; those map 1:1 to the fields above.)

## Setup

1. **Ask the user for the audited org's API key** if not already configured, and use it to set up (or point) the `noveum` MCP server / REST calls at that org — this is where `organizationSlug` + `datasetSlug` (top-level fields in the report JSON) live, and where the dataset items must be fetched from.
2. **Traces**: a report item's trace may live in the audited org, or in the main org. For the main org, use `$NOVEUM_API_KEY` (from the environment or a local `.env`). Try the audited org first; fall back to the main-org key if the traceId 404s there.
3. Determine `novasynth_item_type` per item up front (blank/`agent` = noveum-trace item with full step spans; `novasynth` = transcript-only, sim-bot-as-user).

## Audit flow

Run the phases below **in order** — each phase's survivors feed the next.

### Phase 1 — Item attribution verification

For every recommendation, fan out **one subagent per `(issue, item_id)` pair** — never batch multiple items into one subagent call, since a bad attribution needs to be caught individually.

Give each subagent:
- The full recommendation text (title, description, the specific claim being checked).
- The full dataset item as stored (fetch via the dataset item endpoint — same shape the platform scored on).
- If `novasynth_item_type` is `novasynth`: the raw transcript only. Remind the subagent that user turns are sim-bot-generated verbatim and agent turns are a transcription of the real agent — read accordingly, don't demand transcription-perfect fidelity from the agent side.
- If blank/`agent`: the noveum-trace spans for that item's `traceId` (STT/TTS/LLM spans, tool calls) — fetch the trace so the subagent can see the actual execution path, not just a flattened transcript.
- Permission (and instruction) to fetch the audio via `audio_uuid` from the platform if needed to verify a claim that depends on audio signal (tone, pacing, mispronunciation, etc.) — this applies to LLM-judged and latency-based claims. **Audio-metric scorers themselves (stt_efficacy, mos, gibberish, tone_clarity, pronunciation, latency-as-audio-artifact) are out of scope for verification** — do not have the subagent try to adjudicate those; instead have it explicitly say "cannot verify — audio-metric scorer" so it gets flagged, not silently dropped.

Ask each subagent for a single verdict: **ATTRIBUTED / NOT ATTRIBUTED / UNVERIFIABLE (audio-metric)**, with a one-line quote-backed reason.

**Aggregate per issue:**
- Keep only items marked ATTRIBUTED.
- Items marked NOT ATTRIBUTED are dropped from that issue.
- Items marked UNVERIFIABLE are dropped from the *verified* count but listed separately as "could not verify" — do not treat them as failures of the issue.
- If an issue ends up with **zero** ATTRIBUTED items after this pass, flag the whole issue **for removal** in the final table (don't proceed to phases 2–3 for it, except to note why it's being dropped).

### Phase 2 — Affected-scorer sanity check

For each issue that survived Phase 1 (has ≥1 attributed item), check whether `affected_scorers[]` is actually the right set:
- Do the surviving attributed items show these scorers scoring low (or failing) in their scorer results? Pull actual scorer results for those items, don't trust the report's claim.
- Are there other scorers that *should* be listed but aren't (the issue clearly implicates them but they're missing from `affected_scorers`)?
- Flag: scorers listed but not actually low → **spurious**; scorers that should be listed but aren't → **missing**.

### Phase 3 — Fix sanity check

For each issue still standing, evaluate `action_items[]` given the issue + surviving items + real scorer results:
- **Altitude check**: is this a prompt-level issue being given a pipeline-level fix (or vice versa)? NovaPilot systematically over-engineers here — call out when a one-line system-prompt instruction would fix what's being proposed as a new pipeline stage/guard, and vice versa when a structural/deterministic problem is being handed a "tell the model to try harder" prompt patch.
- **Plausibility**: does the fix actually address the root cause shown in the items, or just the symptom in the title?
- **Blast radius**: could this fix plausibly break other flows/scenarios not covered by the attributed items? Note specific concerns (e.g. "banning this phrase outright will also suppress it in the one scenario where it's required").

## Final report format

One table, one row per original recommendation:

| Issue | Items in / kept / dropped | Scorer verdict | Fix verdict | Notes |

Then below the table:
- **Issues flagged for removal** (0 attributed items survived) with the reason.
- **Unverifiable items** (audio-metric scorers) called out separately, not counted against the issue.
- **Scorer mismatches** (spurious / missing) per surviving issue.
- **Fix concerns** (altitude mismatch, blast radius) per surviving issue.
