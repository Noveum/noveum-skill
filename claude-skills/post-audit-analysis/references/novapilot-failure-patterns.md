# Registered NovaPilot failure patterns

Register only specific, recurring mechanisms. A valid pattern should already answer “what exactly is happening?” Do not use broad consequences such as false premise, mixed attribution, nonexistent reference, wrong altitude, or unusable fix.

## `unmarked-interruption-treated-as-complete-turn`

The captured assistant response is interrupted, truncated, or only a meaningless fragment, but the dataset does not provide usable interruption/barge-in marking. A scorer evaluates the fragment as though it were the assistant's intentional, completed response and penalizes missing content, follow-up, or task completion.

Match only when both conditions are evidenced: the turn is interruption/fragment-confounded, and the scorer's criticism depends on treating it as complete.

## `scorer-judges-last-turn-in-isolation`

The scorer has relevant earlier conversation context but evaluates only the latest user input and assistant output. It therefore misreads resumed speech, acknowledgements, clarification, waiting, closing, or anaphoric replies because it ignores the active conversational state.

This is broader than interruption handling but still requires direct evidence that earlier turns change the correct interpretation.

Known evidence: `docs/scorer_myopic_last_turn_evaluation.md`.

## `reasoning-validator-accepts-invalid-scorer-result`

The reasoning validator receives enough item evidence to see that a scorer's factual claim, numeric score, or score-reasoning relationship is wrong, yet marks that scorer result valid and allows it into downstream grouping and analysis.

Do not match merely because a scorer is wrong. Show the validator input, the contradiction available inside it, and the validator's accepting verdict.

Known evidence: `docs/reasoning_validator_three_axis_proposal.md`.

## `novapilot-overbuilds-narrow-fix`

NovaPilot identifies a narrow observed defect but proposes a much larger algorithm containing unsupported keyword gates, thresholds, scripts, retry counters, escalation branches, state transitions, or new workflow machinery. The extra machinery is not justified by the cited items and makes the recommendation unsafe or impractical as written.

Do not match merely because a recommendation is long. Identify the unsupported mechanisms added beyond the demonstrated defect.

Known evidence: `docs/novapilot_overengineered_prompt_recommendations.md`.

## Registry rules

- Require direct evidence for the complete mechanism.
- Keep near-matches in `Others`.
- After three distinct supported chat-local occurrences of an unregistered mechanism, ask the user before adding it.
- Do not add, remove, merge, or rename patterns without explicit user approval.
