---
name: novapilot-analyzer-audit
description: "Audit what NovaPilot's analyzers actually produced, using the dev_mode artifacts rather than the finished report — raw analyzer recommendations, the consolidation merge, and the payload each analyzer was given. Verifies whether each recommendation's premise is true against the item's own fields, whether its fix is buildable, which of the documented fix patterns it followed, and where quality is lost between stages. Use when the user asks why the recommendations are bad, what the analyzer is doing, whether a prompt/pipeline change helped, or wants to compare two runs at the analyzer level."
trigger: /novapilot-analyzer-audit
---

# NovaPilot analyzer audit

`/novapilot-audit` checks the finished report. This skill goes upstream of it: the report can only be as good as the recommendations entering it, and most defects originate in the analyzer call, not in report assembly. Requires a run made with `dev_mode=True`.

## Usage

```
/novapilot-analyzer-audit <path/to/reports/<org>/<timestamp>>
```

## Where everything lives

```
<run>/dev_artifacts/
  analysis/<agent_slice>/<category>/
      batch_<category>_batch_N_chunk_M_of_K.json   one analyzer LLM call
      consolidation.json                            present only for multi-batch categories
  metric_analysis/group_*.json                      the metric analyzer, a separate path
  grouping/  reasoning_validator/  summarization/  report_pipeline/
```

Each `batch_*.json`:
- `agent` — **`prompt_agent`** or **`tool_agent`**. Always split results by this; they have different jobs and different failure modes.
- `inputs.prompt.text` — the COMPLETE prompt the analyzer saw: its instructions, the fix patterns, and the filtered bad-scores payload.
- `outputs.recommendations[]` — `issue_description`, `current_state`, `recommended_change`, `justification`, `affected_items`, `search`, `replace`, `fixType`, `recommendation_type`.

`consolidation.json`: `inputs.input_recs` (a count), `inputs.prompt.text`, and `outputs.structured_response` — JSON with `recommendations[].merged_from`, indices into the concatenated batch outputs in sorted `batch_*.json` order.

## Rule zero — measure the payload, not the dataset

**The single most common way to get this wrong.** What a scorer shows on a dataset item is not what the analyzer was given. The pipeline filters to low scores and routes deterministic scorers to the metric analyzer, so a scorer that fails all over the dataset may reach a given analyzer almost never. Derive the scorer list per batch and check it before asserting any scorer influenced anything.

Any claim about analyzer behaviour must be computed from `inputs.prompt.text`, e.g.:

```python
i = text.find('## Bad Scores Data')
scorers = set(re.findall(r'"scorer"\s*:\s*"([^"]+)"', text[i:]))
```

Computing it from `item['scorer_results']` instead produces confident, wrong answers.

## Before blaming the analyzer, check what it was handed

An analyzer that faithfully repeats a false scorer claim has a different problem from one that invents things, and the fixes are opposite. So for any rec whose premise fails, decide which it is:

- **inherited** — a scorer's `reasoning` asserted the failure, and the item's own fields (`tool_calls`, `output_text`, `system_prompt`, `tool_call_results`) contradict it
- **invented** — no scorer said it; the analyzer asserted it unprompted

Report the two separately. Never assume either without checking this run's data — scorer reliability and item construction vary by dataset and by ETL version, and a defect that dominated one run may be absent from the next.

Worth a quick deterministic pass each time, since these are cheap and have bitten before: do scorer claims about missing tool calls survive a check against `tool_calls`; is `tool_call_results` populated; does `system_prompt` belong to the same agent node that produced `output_text` (a giveaway is near-identical `output_text` across items differing only in a name or number).

## Cover every analyzer, every time

Three analyzers write recommendations and they fail differently. Auditing only the loudest one gives a misleading headline, and volume is a poor guide to importance — a run can be 95% `prompt_agent` by count while the tool and metric recs are the ones reaching the customer.

| analyzer | `agent` field | artifacts |
|---|---|---|
| prompt | `prompt_agent` | `analysis/*/*/batch_*.json` |
| tool | `tool_agent` | `analysis/*/*/batch_*.json` |
| metric | `metric_analyzer` | `metric_analysis/group_*.json` |

The metric analyzer has a different shape: one call per metric group (latency, speech_signal, interruptions), with `inputs.group`, `inputs.example_item_ids`, `inputs.prompt`, and `outputs.structured_response`. It reasons over pre-computed aggregates rather than per-item scorer prose, and its recs are stamped `source: metric_analysis` in the report.

Judge all three on the same rubric and score them separately. The prompt and tool analyzers each carry their own `## Fix Patterns` block, so each gets its own on/off-guideline breakdown against its own list. An analyzer whose prompt has no such block gets premise and fix only — check, don't assume which.

## The rubric — three axes, always separated

Collapsing these hides which half is broken.

- **premise_true** — is the described problem actually in the cited items? Check `tool_calls`, `output_text`, `system_prompt` and `scorer_results` **directly**, never the scorer prose alone.
- **fix_makes_sense** — would applying it reduce the failure without breaking required behaviour, and does everything it references exist?
- **usable** — hand it to an engineer as-is? Requires both of the above **and** sound attribution (every cited item shows it; any `search` anchor exists in every cited item's prompt).

### Be aware of bias induced by the prompt

The judge answers the question you asked, including the parts you did not mean to ask. A prompt that mentions a prior negative verdict, or that frames the task as explaining a failure, produces near-total agreement with that framing regardless of the evidence.

Judge prompts must say *"verify, do not assume in either direction"* and *"say sound when it is sound."*

**Detector.** Always include a verdict that means "this is fine" — `fix_is_sound`, `usable: true` — and then check how often it was chosen. If it is chosen **zero** times across a whole batch, treat the run as leading rather than the recs as uniformly bad, and rewrite the prompt before quoting any number from it.

## Procedure

### 1. Inventory (deterministic, no agents)
Recs per `agent` — including `metric_analyzer` from `metric_analysis/` — then per agent slice; `recommendation_type`; how many carry `search`/`replace` versus falling back to narrative; scorers present in each batch payload.

*Reading scorer health, for context.* `scorerFailureRates` in the report carries three numbers per scorer, computed in `json_report_generator.py`: `evaluationCoverage = evaluatedItems / totalItems`, `failureRateWithinScored = failedItems / evaluatedItems`, and `failureRateAcrossAllItems = failedItems / totalItems`. `evaluatedItems` counts only rows that produced a real score, so scorers that error out are already excluded from it. A scorer can therefore look healthy on the within-scored rate while having run on a small slice of the dataset — on the aug-2026 run `parameter_correctness` read 4.0% within-scored at 14.6% coverage. Quote the coverage alongside any failure rate.

### 2. Fix-shape taxonomy (per analyzer)

**Read the patterns out of the prompt; never hardcode them.** They live in the analyzer prompts and get edited — an audit against a stale list is worse than no audit, because it silently mislabels new patterns as off-guideline.

**Each analyzer ships its own pattern list.** Extract per batch and group by hash; do not assume one list covers the run. Match on the bold lead only — some bullets carry a parenthetical before the arrow, so anchoring on `→` silently drops them:

```python
blocks = {}                                   # hash -> (block, agent, count)
for bf in glob.glob(f'{root}/*/*/batch_*.json'):
    d = json.load(open(bf)); t = d['inputs']['prompt']['text']
    i = t.find('## Fix Patterns')
    if i < 0:
        continue                              # analyzer ships no patterns; skip pass A for it
    blk = t[i:t.find('\n## ', i + 5)]
    blocks.setdefault(hashlib.sha256(blk.encode()).hexdigest()[:12],
                      (blk, d.get('agent'), 0))
patterns = [m.group(1) for m in re.finditer(r'^\s*-\s+\*\*(.+?)\*\*', blk, re.M)]
```

Sanity-check the count against the block by eye before using it, and report which analyzer each list belongs to. Score every analyzer against **its own** list — never the prompt analyzer's list applied to another, which manufactures a 0% and hides the real result.

Then classify in two passes:

**Pass A — against that analyzer's extracted list.** Build the classifier's enum from its `patterns` at runtime, plus a single `OFF` escape. Classify from the **fix content**, not the justification: the prompt asks the analyzer to name the pattern it applied, but few do, and saying so is no evidence of doing so. Also record, per rec, whether the fix genuinely does what the pattern prescribes — a rec that appends "examples" already present verbatim in the prompt is not a few-shot fix.

**Pass B — cluster what fell out.** Do NOT slot the `OFF` recs into a fixed taxonomy. Feed them to an agent that reads them together and proposes emergent categories with counts and one example each, then reuse those labels for the rest. The off-guideline shapes are the interesting finding — they tell you what the analyzer reaches for when the sanctioned patterns don't fit, and they will differ per run, per agent and per dataset.

Report on-guideline versus off as a share, which extracted patterns went **unused**, and the emergent off-guideline categories. Batch ~8 recs per agent; this pass needs no item files.

### 3. Soundness (all three analyzers)
One agent per rec with up to 3 cited items. For metric recs, cite `inputs.example_item_ids` and judge the claim against the aggregate it was derived from as well as the items. Same rubric, and **one model across every arm you intend to compare** — Sonnet judges noticeably stricter than Opus, enough to move a headline number by 10+ points.

### 4. Stage loss (only when asked where quality is lost)
Sample raw analyzer recs that fed consolidation, the consolidation outputs (derive their items from the inputs their `merged_from` cites), and the final report entries. Judge all three with one rubric and one model, instructing the judge to ignore formatting and polish — the stages differ in shape, not just quality. On the aug-2026 run this came out 25% / 29% / 20% usable: flat, i.e. nothing lost downstream.

### 5. Failure modes and guardrails
For recs where the premise was right but the fix wasn't, extract per case: the specific unverified assertion (quoted), which field already in the payload would have exposed it, a mechanically checkable rule that would have stopped it, and where the rule belongs — analyzer prompt, output schema, deterministic post-check, or more context. Ask for a reusable `guardrail_family` label so cases collapse into a handful of rules.

## Reporting

Lead with the three-axis table split by `agent` — prompt, tool, metric — and, for the prompt analyzer, by fix shape. Then:
- fix shapes used, and which documented patterns were **never** used
- premise failures, separating inherited-from-scorer from analyzer-invented
- fix failures by mode
- proposed guardrails, grouped by family, each with the case count behind it

State which model judged, and which object each number is computed on. When comparing runs, re-judge both with the same model — never quote a number produced by a different judge alongside a new one.

## Baseline — BHFL, 1,031 items, 2026-08-12

For comparison, not as a target.

| | value |
|---|---|
| raw analyzer recs | 158 (150 `prompt_agent`, 8 `tool_agent`) + 3 metric groups |
| on-guideline fix shapes | 53% |
| largest off-guideline cluster | "new pipeline component", 35% |
| patterns never used | 4 of the 10 then in the prompt |
| usable (Sonnet) | 25% analyzer / 29% consolidated / 20% final |
| premise true | ~65% at every stage |
| fix failures | mechanism unsupported 32%, references nonexistent things 32%, breaks other behaviour 18% |
