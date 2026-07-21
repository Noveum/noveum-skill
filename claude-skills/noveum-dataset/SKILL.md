---
name: noveum-dataset
description: Download/upload Noveum datasets, items, scorer results, and audio files via the REST API. Use when the user asks to fetch a dataset by slug, save audio for items, push items/scorer results to a new dataset slug, publish a dataset version, or build pipelines around datasets stored on noveum.ai. Skip for Noveum eval/ETL/NovaSynth operations — those have separate endpoints.
---

# Noveum dataset I/O

Talks directly to the Noveum REST API. **No NovaEval SDK / no app.* imports.** All four scripts are self-contained: `requests` + stdlib + `python-dotenv`. Mirror these curl patterns:

```
GET    /api/v1/datasets/{slug}/items/ids
GET    /api/v1/datasets/{slug}/items/{itemId}
GET    /api/v1/audio/{audio_uuid}
POST   /api/v1/datasets
POST   /api/v1/datasets/{slug}/items
POST   /api/v1/datasets/{slug}/versions/publish
POST   /api/v1/scorers/results/batch
```

Auth is **both** `Authorization: Bearer $KEY` header **and** `apiKeyCookie=$KEY` cookie — the platform requires the cookie for some routes. The scripts handle this.

## When to use

- "Download dataset `<slug>`" → `download_items.py`.
- "Download audio for the items" / "fetch audio_uuids" → `download_audios.py`.
- "Upload this JSON as a new dataset" → `upload_items.py` (creates dataset if absent, batches items, optional publish).
- "Upload scorer results" → `upload_scorer_results.py` (separate endpoint; items POST does NOT carry scorer_results).
- Re-scoring or cleaning a dataset locally and pushing back as a new version: use the full v3 recipe at the bottom.

## When NOT to use

- Running scorers — use the NovaEval `ScorerExecutor` directly, not this skill.
- ETL jobs, eval jobs, NovaSynth runs, telemetry — different endpoints, not covered here.
- Anything that needs DELETE on scorer results / items — the Bearer key typically lacks delete perms; surface that to the user rather than retry.

## API key resolution

Each script tries, in order: `--api-key` flag → `NOVEUM_API_KEY` env → first `*_NOVEUM_API_KEY` env var found in `.env`. `.env` is loaded from the cwd (or `--env-file`). For project-scoped keys (e.g. `<PROJECT>_NOVEUM_API_KEY`), pass `--env-key <PROJECT>_NOVEUM_API_KEY` or export `NOVEUM_API_KEY` first.

## Important schema gotchas

- **Items POST** wraps "flat" export rows: nest `agent_name`, `system_prompt`, `latency`, `stt_data`, `tts_data`, etc. inside `content`. `source_trace_id` → `trace_id`, `source_span_id` → `span_id`.
- Items POST **rejects nulls** for typed fields — `upload_items.py` substitutes the API's defaults (`""`, `[]`, `{}`) for any None. Don't strip this normalization.
- **Items POST does NOT accept scorer_results** — they live at a separate endpoint. If a user expects scores to upload alongside items, run both scripts.
- **Scorer-results endpoint uses camelCase** (`datasetSlug`, `itemId`, `scorerId`, `scorerName`), `passed` is a **boolean** (not 0/1), and `metadata` is an **object** (not a JSON string).
- Some array fields in the export are stored as a single dict (one stt event per item). `upload_items.py` wraps single dicts in `[v]` for known array fields (`stt_data`, `vad_metrics`, `*_metrics`, `tool_calls`, …).

## Probing the API safely

If you need to discover an undocumented field shape, **probe against a throwaway slug** like `__probe__skill_test`, not the user's real dataset. Orphan probe rows on a production slug are visible in admin listings and embarrassing.

## Scripts

All live in `scripts/` next to this SKILL.md. Help text via `--help`. Typical invocations:

```bash
# 1) Download all items of a dataset to JSON.
NOVEUM_API_KEY=$KEY python scripts/download_items.py \
    --slug pocbhflbotmay26 \
    --output ./out/pocbhflbotmay26.json \
    --workers 10

# 2) Download audios referenced inside a dataset JSON
#    (extracts every audio_uuid found in stt_data, tts_data, raw_complete_audio).
NOVEUM_API_KEY=$KEY python scripts/download_audios.py \
    --input ./out/pocbhflbotmay26.json \
    --output-dir ./out/audio \
    --workers 10
# Or pass UUIDs explicitly:
NOVEUM_API_KEY=$KEY python scripts/download_audios.py \
    --uuids 70864d3e-... 9369b0a5-... --output-dir ./audio

# 3) Upload items to a new dataset slug (creates + batches + optional publish).
NOVEUM_API_KEY=$KEY python scripts/upload_items.py \
    --input ./out/pocbhflbotmay26.json \
    --slug pocbhflbotmay26-v4 \
    --name "POC BHFL Bot May26 v4" \
    --project-id poc-voice-single-agent \
    --environment production \
    --dataset-type agent \
    --batch-size 50 \
    --publish

# 4) Upload scorer_results for that same dataset.
NOVEUM_API_KEY=$KEY python scripts/upload_scorer_results.py \
    --input ./out/pocbhflbotmay26.json \
    --slug pocbhflbotmay26-v4 \
    --batch-size 100
```

## Re-uploading a cleaned dataset (recipe)

When the user has locally rescored / pruned an export and wants it on the platform as a fresh version:

1. Pick a new slug. Don't reuse the source slug — version it (`-v2`, `-v3`, …) so audits can compare.
2. `upload_items.py --publish` against the new slug. Items live in `next_release` until `--publish` is set.
3. `upload_scorer_results.py` against the same slug. The two endpoints are decoupled; do not try to bundle.
4. Verify via `GET /api/v1/datasets/{slug}/items?limit=1` and `GET /api/v1/scorers/results?datasetSlug={slug}&limit=2`.

## Failure modes worth knowing

- 401 on POST: key valid but lacks the role; tell the user, don't retry.
- 400 with Zod `invalid_type` errors: a field's shape disagrees (array vs object, null vs string). The normalization in `upload_items.py` covers the common cases — if a new one appears, add the field to the right defaults/array_fields set rather than catching the error.
- Bedrock 504s / Gemini DEADLINE_EXCEEDED on parallel downloads: harmless, scripts retry with backoff. Don't lower workers below 3.
- Empty `items[]` on a freshly created dataset: items are in `next_release`; `--publish` moves them to `current_release` and they then appear in default GET responses.
