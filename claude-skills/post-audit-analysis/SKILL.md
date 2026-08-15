---
name: post-audit-analysis
description: Analyze unusable or false-premise NovaPilot recommendations after an audit, classify them against a small registry of specific recurring failure mechanisms, surface unmatched cases for manual review, trace those cases through items, scorers, validators, grouping, analyzers, consolidation, and ETL, and create reproducible Markdown evidence files for newly discovered root causes. Use when deciding which audited recommendations deserve manual inspection, hunting for new NovaPilot failure patterns, or documenting why recommendations became unusable.
---

# Post-audit analysis

Use the completed NovaPilot audit as the candidate list. Identify recommendations explained by precise, already-established failure mechanisms, then manually investigate the remainder to discover new mechanisms and their root causes.

A **NovaPilot failure pattern** must be specific and repeatable. Its definition must already answer “what exactly is happening?” Generic outcomes such as false premise, mixed attribution, wrong altitude, nonexistent reference, or unusable fix are not patterns; they are consequences that many unrelated mechanisms can produce.

This skill follows, rather than replaces, `novapilot-audit` and `novapilot-analyzer-audit`. Read the complete `novapilot-analyzer-audit` skill before tracing analyzer artifacts.

## Required resources

Read [references/novapilot-failure-patterns.md](references/novapilot-failure-patterns.md) completely before classifying recommendations.

Before launching classification subagents, read and follow [references/review-artifact-schema.md](references/review-artifact-schema.md). Every reviewer verdict must be persisted; mailbox output alone is not a completed review.

When documenting a newly established cause, copy and complete [assets/root-cause-template.md](assets/root-cause-template.md).

## Inputs

Locate or request:

- the completed audit output;
- the NovaPilot run and `dev_artifacts/` directories;
- dataset and organization names;
- detailed and final reports when relevant;
- source items or audit case files.

Do not rerun the complete audit. Continue from its unusable and false-premise recommendations unless the user explicitly requests a fresh audit.

## Workflow

### 1. Inventory and classify with subagents

List every recommendation marked unusable or premise-false. Preserve analyzer, recommendation ID, category, affected item IDs, scorer names, and source artifact path.

Create a timestamped analysis directory beside the audit using the layout in `review-artifact-schema.md`. Write `manifest.json` before spawning reviewers. Record the audit, run, registry, candidate list, judge model, and their hashes so an interrupted run can be resumed without repeating completed reviews.

When parallel review is requested, assign one recommendation to one subagent and use the same judge model for all. Give each subagent the registry, audit entry, and only the raw artifacts needed for that recommendation. Require verification against items and dev artifacts rather than trusting the audit verdict or category name.

Require each subagent to return:

- `recommendation_id`;
- `matched_patterns`: exact registry IDs supported by direct evidence;
- `unmatched_failure_modes`: specific mechanisms not explained by the registry;
- `worth_manual`: `true` exactly when `unmatched_failure_modes` is non-empty;
- item, scorer, validator, and artifact evidence sufficient to verify the decision.

Require each subagent to write its complete decision to its unique `reviews/<recommendation-id>.json` file before returning. Store its evidence-based rationale, audit snapshot, matched and unmatched mechanisms, exact artifact references, uncertainties, missing evidence, and any extra findings—not merely the final labels. Do not request or store private chain-of-thought; store a concise, reviewable claim/evidence/inference rationale instead.

Treat the saved JSON file as the source of truth. A mailbox response is only a completion notification. Validate every review against the schema before counting it. If the run is interrupted, reuse valid reviews whose recorded audit, registry, recommendation-artifact, and model hashes still match; rerun only missing, invalid, or stale reviews.

### 2. Apply a strict pattern-match test

Match a pattern only when its complete mechanism is supported. Do not match merely because it could lead to the same final audit verdict.

For example:

- Do not map every false premise to scorer myopia; show that the scorer ignored available earlier conversation context.
- Do not map every incomplete response to interruption confusion; show that the captured turn was interrupted or fragmentary and lacked usable interruption marking.
- Do not map every bad scorer result to validator failure; show that the reasoning validator received enough contradictory evidence and still accepted it.
- Do not map every long recommendation to an overbuilt fix; show unsupported gates, scripts, thresholds, retries, branches, or state machinery beyond the demonstrated defect.

A recommendation belongs in `Others` when no registered mechanism fully explains it, or when it contains any additional material mechanism outside the registry. Partial pattern matches do not remove it from `Others`.

Do not use regex, filename, report category, or surface-symptom matching as proof.

### 3. Report the pattern-count table immediately

As soon as all classification subagents return and their saved reviews validate, assemble a stable, recommendation-sorted `classifications.jsonl` from the individual JSON files. Never let concurrent reviewers append to the shared JSONL file. Also write `summary.json` containing counts, fully explained IDs, the ordered `Others` queue, and links to the source review files.

Then show every registered pattern, including zero-count rows, followed by `Others`:

| NovaPilot failure pattern | Occurrences | Recommendation IDs |
|---|---:|---|
| `<every registered pattern>` | `<count>` | `<IDs or —>` |
| **Others** | `<count>` | `<IDs>` |

Count one occurrence when one recommendation directly demonstrates that pattern. Classification is multi-label. Count a recommendation in `Others` once when it has at least one unmatched mechanism, even if it also matches registered patterns; row counts therefore need not sum to the recommendation total.

Immediately state:

- total recommendations classified;
- recommendations fully explained by registered patterns;
- `Others` requiring manual inspection;
- the ordered `Others` queue.

Also report the analysis-directory path so the user can inspect every reviewer decision and its evidence.

Pause after the table. Treat `Others` as the default manual-review queue and let the user choose or confirm the order.

### 4. Trace each `Others` recommendation

Inspect, in order:

1. Actual item: conversation, input/output, prompt, retrieved context, tool calls, and tool results.
2. Each implicated scorer: score, reasoning, and factual claims.
3. Reasoning validator: input, verdict, and missed contradiction.
4. Grouping: seeded assignment, cleanup assignment, and evidence shown to the grouping model.
5. Raw analyzer call: payload, premise, affected items, fix, and `search`/`replace`.
6. Consolidation and report merger when attribution or wording changed.
7. Raw trace or source dataset when normalized representations conflict.

Prefer raw evidence over lossy normalized fields, while recording both representations. Stop at the earliest supported cause that explains the downstream recommendation failure. Separate the primary cause from contributing factors.

### 5. Document each unique root cause

Create one Markdown file per unique supported cause found during manual review. Default to `<repository>/docs/novapilot-root-causes/<root-cause-slug>.md`. Append later occurrences of the same cause to that file rather than creating aliases.

Every file must contain:

- a precise mechanism and explanation;
- the NovaPilot recommendation failure it produced;
- originating and affected pipeline stages;
- dataset and organization names;
- run, audit, and exact `dev_artifacts` paths;
- analyzer and recommendation ID;
- scorer names, scores, and validator results when relevant;
- full item IDs;
- direct evidence and reproduction steps;
- scope, uncertainty, counterexamples, and duplicate-evidence notes;
- chat-local occurrence count and log.

Use repository-relative paths when possible.

### 6. Propose registry additions after three occurrences

Track unregistered mechanisms during the current chat. Count distinct supported occurrences, normally distinct recommendations; duplicate item representations are not independent evidence.

When the same unregistered mechanism reaches **three supported occurrences in the same chat**, ask the user whether it may be added to the registry. Provide the proposed name, a definition specific enough to answer “what exactly is happening?”, and the three occurrences.

Do not edit the registry without explicit approval. Do not add generic consequences such as false premise, mixed attribution, nonexistent reference, wrong altitude, or unusable fix.

## Reporting each manual checkpoint

Show, before concluding:

1. What NovaPilot said and proposed.
2. What the cited items actually show.
3. What the scorers and validator said.
4. How grouping, analyzer, consolidation, and ETL contributed.
5. The precise recurring mechanism or why it remains unique/inconclusive.
6. The root-cause evidence-document path.

Analyze only; do not propose product fixes unless the user asks.
