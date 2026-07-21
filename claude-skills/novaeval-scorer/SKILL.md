---
name: novaeval-scorer
description: Add a new scorer to the NovaEval repo end-to-end — implement the BaseScorer class and register it in ALL the required places (package __init__, the app.utils name→class map, model-dependency set, ScorerType enum + ScorerFactory if a new type, docs YAML, tests). Use when the user asks to create/add/port/register a NovaEval scorer, wire a scorer into the executor/config, or asks "where do scorers get registered". Repo: NovaEval (has src/novaeval/scorers/ and a vendored app/ package).
---

# Add a NovaEval scorer

> **Internal / contributor tooling.** This skill edits the **NovaEval source repo** itself (a local checkout with `src/novaeval/` and the vendored `app/`). It is not a platform/API skill — use it only when working inside the NovaEval codebase.

Registration is spread across **5–8 files**. Miss one and the scorer either won't be discoverable, won't instantiate, or won't route correctly. Work the checklist below in order. Paths are relative to the NovaEval repo root.

## 0. Decide: simple vs complex

The executor (`src/novaeval/executor/scorer_executor.py`) classifies every scorer by calling `scorer.get_config()`:

- **Complex** (`get_config()` returns `None`, the `BaseScorer` default): run individually via `ComplexScorerRunner` → calls `score(item)` (or async `evaluate(item)`). Use for pure-compute/DSP scorers, anything with bespoke logic, or non-grouped LLM logic. **Don't override `get_config`.**
- **Text-simple** (`get_config()` returns a dict, no `audio_key`): groupable into one batched LLM call.
- **Audio-simple** (`get_config()` returns a dict with `audio_key`): grouped multimodal (LLM) audio path; the audio is extracted by `src/novaeval/executor/audio_registry.py` (`AUDIO_EXTRACTORS`, keyed by `audio_key` like `stt_single`, `user_mono`, `tts_clip`). Only for LLM-judged audio.
- **Post-run** (`item_summary` type): runs after all peers; not with other complex scorers.

A DSP/no-LLM scorer is almost always **complex**. A pure-compute scorer must NOT emit an `audio_key` or it misroutes to the LLM path.

## 1. Implement — `src/novaeval/scorers/<your_scorer>.py`

```python
from novaeval.scorers.base import BaseScorer, ScoreResult
from novaeval.scorers.constants import ScorerErrorScore, ScorerThreshold
from novaeval.standard_data import StandardData
from novaeval.utils.exception_handling import handle_missing_field_error, handle_unknown_error

class MyScorer(BaseScorer):
    def __init__(self, name="my_scorer", threshold=ScorerThreshold.DEFAULT.value,
                 model=None, **kwargs):   # accept-and-ignore `model` if no LLM needed (see §4)
        super().__init__(name=name, **kwargs)
        self.threshold = threshold
        self.model = None                 # set so the complex runner skips LLM-usage metadata
    # complex scorer: do NOT override get_config (inherits -> None)
    def score(self, data: StandardData) -> ScoreResult:
        try:
            # validate inputs; on missing fields return handle_missing_field_error(...)
            ...
            return ScoreResult(score=val, passed=val >= self.threshold,
                               reasoning="...", metadata={...})
        except Exception as e:
            return handle_unknown_error(exception=e, scorer_name=self.name,
                                        failure_location="my_scoring", data_type="StandardData")
```

Conventions (match them or the platform misreads results):
- **Score direction: higher = better.** `passed = score >= threshold`. Default threshold `ScorerThreshold.DEFAULT.value` (7.0) on a 1–10 scale.
- **Defect detectors invert.** If your raw signal is "higher = worse" (robotic, breakage, gibberish), report `score = 11 - raw_1_10` (or similar) so high=good, and keep the raw index in `metadata`. Precedents: `AudioBreakageScorer`, `STTOverSuppressionScorer`.
- **Errors return, never raise.** `ScorerErrorScore.ERROR_SCORE.value` is `-1.0`. Use the `handle_*` helpers in `src/novaeval/utils/exception_handling.py` for actionable reasoning.
- **Heavy imports** (`librosa`, big models): import lazily inside functions. `numpy`/`soundfile`/`requests` are already hard deps. `scorers/__init__.py` imports every scorer eagerly — a failing top-level import takes down the whole package.

Audio scorers: fetch bytes by UUID/URL via `novaeval.utils.audio_utils.get_audio_bytes_for_multimodal_scorer(audio_uuid=multimodal_fetch_uuid(uuid), audio_url=url)`. Relevant `StandardData` fields live on `STTData` / `TTSData` / `RawCompleteAudio` in `src/novaeval/standard_data/standard_data.py` (e.g. `audio_uuid`, `audio_url`, `raw_audio_uuid`). Those models use `extra="ignore"` — **add an explicit field** for new data; do NOT flip to `extra="allow"` (system-wide convention; spans are attribute-heavy). `metadata.local_audio_path` is the sanctioned local-file override.

## 2. Export — `src/novaeval/scorers/__init__.py`

Add `from novaeval.scorers.<your_scorer> import MyScorer` and add `"MyScorer"` to `__all__` (keep `__all__` sorted — ruff isort enforces import order).

## 3. Name→class map — `app/utils/scorer_registry.py`  ← the easily-missed one

`app/` is **vendored in the repo** (not a separate package — you CAN edit it). The factory looks the scorer up by `scorer_config.name` in a category map. Add your name (+ aliases) to the right `get_*_scorer_map()`:

| category | function | model passed by factory? |
|---|---|---|
| audio (incl. STT/TTS multimodal & DSP) | `get_audio_scorer_map` | yes (`model=...`) |
| latency / duration (pure compute) | `get_latency_scorer_map` | no |
| safety / bias / nlp_metrics / format_validation | `get_*_scorer_map` | varies |
| conversational / telephony / rcbc_collections | `get_*_scorer_map` | yes |
| rag pipeline | `get_rag_pipeline_evaluator_map` | yes |

The factory branch is in `src/novaeval/config/job_config.py` (`ScorerFactory.create_scorer`). For existing categories it calls `scorer_map[name](model=model, threshold=..., **params)` and falls back to a no-`model` call on `TypeError`. Add aliases (canonical `my_scorer` + any short/UI name) like the existing entries.

## 4. Model-dependency — `app/utils/scorer_utils.py` (`_get_model_dependent_scorers`)

This set is keyed by **`ScorerType`** (not name). If your scorer's type is in it, the executor *requires* a model to be configured (else it errors at construction). `AUDIO`, `SAFETY`, `BIAS`, `AGENT`, `TELEPHONY`, etc. are in it; `LATENCY`, `NLP_METRICS`, `FORMAT_VALIDATION` are not.
- No-LLM scorer under a model-dependent type (e.g. `audio`): make `__init__` accept-and-ignore `model=None` (§1). It works as long as a model is present (usually true — jobs rarely run one scorer alone). If you want it truly model-free, register under `latency` (not in the set) instead.

## 5. New ScorerType (only if not reusing an existing type)

Most scorers reuse an existing `scorer_type` (e.g. `audio`). Only if you need a brand-new one:
- Add the enum value to `src/novaeval/config/schema.py` (`class ScorerType`).
- Add a matching `elif scorer_type == ScorerType.X:` branch in `ScorerFactory.create_scorer` (`src/novaeval/config/job_config.py`).
- Consider adding it to `MODEL_DEPENDENT_SCORERS` (§4).

## 6. Docs — `docs/scorers_documentation.yaml`

Add a top-level key `<your_scorer>:` with `scorer_file`, `scorer_type`, `overview`, and a `scorers:` list of `{name, required_fields[], optional_fields[], description}`. Copy the shape of a nearby entry (e.g. `stt_efficacy_scorer:`). State required `StandardData` fields explicitly — this is what mapper/dataset authors read.

## 7. Tests — `tests/unit/test_<your_scorer>.py`

`pytestmark = pytest.mark.unit`. Cover: a real score, the missing-field error path (`score == ScorerErrorScore.ERROR_SCORE.value`), and any decode/fetch failure path. For audio, mock `novaeval.scorers.<your_scorer>.get_audio_bytes_for_multimodal_scorer` to return synthesized bytes. **Test direction, not just "it runs"** — assert a degraded/worse input scores lower than a clean one (a symmetric/identical-input test can't catch a swap or sign flip).

## 8. Verify

```bash
python -c "from novaeval.scorers import MyScorer; s=MyScorer(); print(s.get_config())"  # None => complex
python -c "from app.utils.scorer_registry import get_audio_scorer_map as m; print('my_scorer' in m())"
python -m pytest tests/unit/test_<your_scorer>.py -q
ruff check src/novaeval/scorers/<your_scorer>.py src/novaeval/scorers/__init__.py app/utils/scorer_registry.py
```

## Gotchas seen in practice

- **Audio fetch endpoint:** `get_audio_bytes_for_multimodal_scorer` with a UUID and no pre-signed URL hits the Noveum platform API at `GET /api/v1/audio/{id}/serve` (the bare `/api/v1/audio/{id}` returns JSON metadata, not audio). Needs `NOVEUM_API_KEY` or `EXOTEL_API_KEY`.
- **Cache poisoning:** downloads cache under `/tmp/noveum/audio_files/{uuid}.wav`. If a bad fetch cached a non-audio blob, clear that file before retrying (or `NOVEUM_AUDIO_CACHE=0`).
- **ETL mapper is separate:** populating new `StandardData` fields from raw spans happens in the (server-side) ETL mapper, not in NovaEval. Adding the field here only makes it *possible*.
