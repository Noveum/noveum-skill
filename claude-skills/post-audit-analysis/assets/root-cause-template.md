# NovaPilot root cause: <precise causal name>

## Status

- Root-cause status: `SUPPORTED | INCONCLUSIVE`
- First observed: `<date or chat context>`
- Supported occurrences in this chat: `<count>`

## Description

<Describe the upstream issue as a precise causal mechanism rather than a generic consequence or surface symptom.>

## NovaPilot recommendation failure produced

- Registered pattern(s): `<one or more IDs from novapilot-failure-patterns.md>`
- Novel pattern candidate: `<specific recurring mechanism or N/A>`
- How the root cause produced the unusable recommendation: `<short causal chain>`

## Pipeline location and impact

- Originating stage: `<scorer | reasoning validator | grouping | analyzer | consolidation | merger | ETL/artifact construction>`
- Affected downstream stages: `<stages>`
- Resulting report failure: `<false premise | mixed attribution | unusable fix | wrong altitude | other>`

## Reproducibility metadata

- Dataset: `<full dataset name>`
- Organization: `<organization name>`
- NovaPilot run: `<repository-relative run path>`
- Dev artifacts: `<exact path(s)>`
- Audit output: `<path>`
- Analyzer: `<prompt_agent | tool_agent | metric_analyzer>`
- Recommendation ID: `<full ID>`

## Evidence

| Item ID | Scorer | Score | Validator result | Evidence |
|---|---|---:|---|---|
| `<full item UUID>` | `<scorer name>` | `<score>` | `<result or N/A>` | `<direct, concise evidence>` |

### What the item shows

<Relevant input, output, conversation state, system instruction, tool call, or tool result.>

### What the scorer and validator claimed

<Exact claim and why it is supported or contradicted.>

### What NovaPilot produced

<Issue description, affected items, and proposed fix.>

### Artifact lineage

<Grouping assignment, analyzer payload/output, consolidation, and report changes as relevant.>

## Root-cause determination

<State the earliest supported cause. Separate contributing conditions from the root cause.>

## How to verify

1. Open `<artifact path>`.
2. Locate `<recommendation/item/scorer key>`.
3. Compare `<fields>`.
4. Confirm `<decisive observation>`.

## Scope, counterexamples, and uncertainty

<State what this pattern does not cover, duplicate evidence, conflicting representations, or missing artifacts.>

## Chat-local occurrence log

| # | Dataset | Recommendation | Item/scorer evidence | Independent? |
|---:|---|---|---|:---:|
| 1 | `<dataset>` | `<rec ID>` | `<item IDs / scorers>` | `yes/no` |
