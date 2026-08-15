# Persistent review artifacts

Persist every post-audit classification so it can be inspected, resumed, and re-aggregated without repeating judge calls.

## Directory layout

Default to a timestamped directory beside the audit:

```text
<audit-directory>/post_audit_analysis/<run-label>-<YYYYMMDDTHHMMSSZ>/
  manifest.json
  reviews/
    <recommendation-file-stem>.json
  classifications.jsonl
  summary.json
```

Use one unique review file per recommendation. Subagents must never append concurrently to `classifications.jsonl`; the parent creates it from validated review files after all reviewers finish.

## `manifest.json`

Write this before spawning reviewers:

```json
{
  "schema_version": 1,
  "status": "running",
  "run_label": "exotel-v7",
  "dataset": "...",
  "organization": "...",
  "created_at": "ISO-8601 UTC",
  "completed_at": null,
  "judge_model": "gpt-5.6-luna",
  "source_paths": {
    "audit": "repository-relative path",
    "novapilot_run": "repository-relative path",
    "dev_artifacts": "repository-relative path",
    "registry": "absolute or repository-relative path"
  },
  "source_hashes": {
    "audit_sha256": "...",
    "registry_sha256": "..."
  },
  "candidate_recommendations": ["full recommendation filenames"],
  "expected_reviews": 31
}
```

On completion, set `status` to `complete` and populate `completed_at`. Preserve an interrupted directory and resume it rather than erasing it.

## Individual review schema

Each subagent must save a valid JSON object with these fields before returning:

```json
{
  "schema_version": 1,
  "run_label": "...",
  "dataset": "...",
  "organization": "...",
  "recommendation_id": "...",
  "recommendation_file": "...",
  "analyzer": "prompt_agent | tool_agent | metric_analyzer",
  "category": "...",
  "reviewer": {
    "task_name": "...",
    "model": "...",
    "completed_at": "ISO-8601 UTC"
  },
  "input_fingerprints": {
    "audit_sha256": "...",
    "registry_sha256": "...",
    "recommendation_artifact_sha256": "..."
  },
  "audit_snapshot": {
    "premise_true": false,
    "fix_makes_sense": false,
    "usable": false,
    "audit_reason": "..."
  },
  "decision": {
    "matched_patterns": ["exact-registry-id"],
    "unmatched_failure_modes": [
      {
        "provisional_name": "specific-mechanism-name",
        "mechanism": "Precise explanation of what happened and at which stage",
        "why_not_registered": "...",
        "evidence_ids": ["E1"]
      }
    ],
    "fully_explained_by_registry": false,
    "worth_manual": true,
    "confidence": "high | medium | low"
  },
  "review_reasoning": {
    "claims": ["Concise factual claims"],
    "evidence_to_inference": ["How cited evidence supports or rejects each mechanism"],
    "alternatives_considered": ["Plausible alternatives and why they do not fit"],
    "uncertainties": ["Anything the artifacts cannot establish"]
  },
  "evidence": [
    {
      "evidence_id": "E1",
      "stage": "item | scorer | validator | grouping | analyzer | consolidation | merger | ETL | raw_trace",
      "path": "exact path",
      "json_pointer": "/precise/field/when/available",
      "item_id": "full item ID or null",
      "scorer": "scorer name or null",
      "value_or_excerpt": "short sufficient excerpt or structured value",
      "relevance": "Why this evidence changes the classification"
    }
  ],
  "missing_or_conflicting_evidence": [],
  "extra_findings": [],
  "errors": []
}
```

The stored rationale must be independently reviewable but concise. Do not store hidden chain-of-thought, secrets, environment variables, entire prompts, or duplicated large payloads. Cite exact paths and JSON pointers, with only the excerpt needed to verify the judgment.

Enforce these invariants:

- `worth_manual` is true exactly when `unmatched_failure_modes` is non-empty.
- `fully_explained_by_registry` is the inverse of `worth_manual`.
- Every matched pattern is an exact current registry ID.
- Every matched or unmatched mechanism cites at least one evidence entry.
- Input hashes match the manifest and current source artifacts.
- A review with errors that prevent classification remains invalid and must not enter counts.

## Aggregates and resumption

After validating all individual reviews:

1. Sort them by analyzer and recommendation ID.
2. Write one complete review object per line to `classifications.jsonl`.
3. Write `summary.json` with registry-pattern counts, multi-label IDs, fully explained IDs, `Others` IDs, invalid/missing reviews, and source review paths.
4. Mark the manifest complete only when no required review is missing or invalid.

For resumption, reuse a review only when its schema validates and its audit, registry, recommendation-artifact, and model fingerprints match the current manifest. Otherwise retain it for provenance but rerun that recommendation into a new timestamped attempt or run directory.
