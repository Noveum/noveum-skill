# Apply fixes to the codebase (step 7)

Input: a fix with a `diff` (`search`/`replace`/`rule`, plus `basePrompt`/`fixedPrompt`, or
`toolChange` for a `tool-schema` fix) from AutoFix, an experiment result, or a NovaPilot
recommendation. Prompt fixes follow sections 1 and 2; a `tool-schema` fix follows
section 3. Output: a minimal, reviewable PR in the customer's repo, applied by YOU, in
THEIR environment. Nothing is sent to Noveum in this step except, later, the ordinary
telemetry that verifies the fix.

## 1. Locate where the prompt lives (three strategies, in order)

1. **Provenance** (when present): newer noveum-trace versions stamp `code.file.path` /
   `code.line.number` / `code.function` and `git.commit.sha` on spans; if the fix carries a
   `sourceRef`, open exactly that location.
2. **Anchor search:** grep the repo for distinctive substrings of `search` (or of
   `basePrompt`). Prompts are often templated/assembled — if the exact string isn't found,
   search for its longest stable fragments and find the template that produces it.
3. **Inference:** locate prompt-construction code (files named like `prompts`, `system`,
   constants passed to `messages=[{"role": "system", ...}]`) and match semantically.

If you cannot confidently locate the prompt, STOP and ask the user — never guess-edit.

## 2. Apply the edit

- `kind: "search-replace"`: replace the `search` text with `replace` at its source
  (template or literal). If the prompt is assembled from fragments, apply the change to
  the fragment that contains the anchor, preserving the template structure.
- `kind: "append-rule"` / `rule`: append the rule text to the system prompt's source in
  the repo's existing style (same formatting, same language as surrounding rules).
- Sanity check: reconstruct the final prompt mentally (or via the repo's tests) and
  compare against `fixedPrompt` — the deployed prompt should match what was backtested.
  Meaningful divergence = flag to the user, don't ship silently.

Also bump the app's `NOVEUM_SERVICE_VERSION` (or however the repo sets `service_version`)
so post-fix traffic is distinguishable — this is what makes verification possible.

## 3. Apply a tool-schema fix

A `tool-schema` fix changes the definition of a tool the agent registers with its model,
not the prompt. AutoFix tested it by patching the tool as the recorded conversations list
it (each dataset item's `tools_available`, the tool list the agent sent the model) and
replaying. `diff.toolChange` lists the patch one edit per line:

| Line | Edit on the registered tool |
|---|---|
| `Tool: <name>` | the tool to change; never rename it |
| `New description: <text>` | replace the whole description with the text |
| `Now required: a, b` | add each name to the parameters' `required` list, after the existing entries |
| `No longer required: c` | remove the name from `required`; the parameter stays, now optional |
| `Parameter <name>: <JSON>` | replace that parameter's whole schema with the JSON (a new name adds a parameter); other parameters stay as they are |

Change nothing else. A tool recorded without a typed parameter schema only takes a
description change.

1. **Locate the definition.** Grep the repo for the tool name and a distinctive fragment of
   its recorded description. It is usually an OpenAI-style `tools=[{"type": "function",
   ...}]` dict, a framework tool whose description comes from a docstring or a
   `description=` argument, or a Pydantic model passed as its argument schema. If several
   agents register the tool, change only the one named by the fix's `agentName`. If you
   cannot find it, stop and ask the user.
2. **Edit it in the repo's own style.** Write the description where the framework reads
   it (the docstring, when that is the description). In a Pydantic argument model a field
   is required when it has no default: give a no-longer-required field a default and drop
   the default of a newly required one. Put a `Parameter` line's `description`, `enum`,
   `pattern` or type on that field. When a parameter becomes required, make sure the
   handler accepts it and every caller passes it.
3. **Compare the emitted schema with the tested schema.** Build the tested schema: the
   recorded definition with the patch applied. Then print the definition the edited code
   sends the model, serialized the way the framework sends it (the dict itself, or the
   framework's own conversion, for example `convert_to_openai_tool` in LangChain), or log
   one real request. Compare `description`, `required` and each property. Keys a
   framework adds on its own, such as Pydantic's `title`, a `default` or
   `additionalProperties`, are not a difference. Any other difference means the agent would run something that was not
   tested: fix the code, or flag it to the user, never ship silently.

**Worked example.** The recorded tool:

```json
{ "name": "lookup_policy",
  "description": "Look up a policy.",
  "parameters": { "type": "object",
    "properties": { "customer_id": { "type": "string" },
                    "region":      { "type": "string" },
                    "policy_id":   { "type": "string" } },
    "required": ["customer_id", "region"] } }
```

The validated fix:

```
Tool: lookup_policy
New description: Look up the customer's policy by its number. Call it before quoting any coverage.
Now required: policy_id
No longer required: region
Parameter policy_id: {"type": "string", "description": "Policy number from the customer's card, like P-123456"}
```

The tested schema is the recorded one with those edits:

```json
{ "name": "lookup_policy",
  "description": "Look up the customer's policy by its number. Call it before quoting any coverage.",
  "parameters": { "type": "object",
    "properties": { "customer_id": { "type": "string" },
                    "region":      { "type": "string" },
                    "policy_id":   { "type": "string",
                                     "description": "Policy number from the customer's card, like P-123456" } },
    "required": ["customer_id", "policy_id"] } }
```

The repo registers the tool from a Pydantic model and a docstring. After a first edit the
emitted schema reads, with `title` keys left out:

```json
{ "description": "Look up the customer's policy by its number. Call it before quoting any coverage.",
  "parameters": { "type": "object",
    "properties": { "customer_id": { "type": "string" },
                    "region":      { "type": "string" },
                    "policy_id":   { "type": "string" } },
    "required": ["customer_id", "region", "policy_id"] } }
```

Two differences: `region` is still required, because its field has no default, and
`policy_id` lacks the tested description. Give `region` a default (`region: str = ""`)
and set `policy_id: str = Field(description="Policy number from the customer's card,
like P-123456")`, emit again, and compare until only such framework keys differ. Then
open the PR.

## 4. Open the PR (never push to the default branch)

Branch + PR with a body containing:
- What was changed and why (the finding, in one paragraph)
- **Evidence**: validation status (validated win w/ CI + objectiveGain / directional /
  unvalidated recommendation), affected checks/scorers, evidence trace/item ids
- Link to the NovaPilot report / AutoFix run in the Noveum dashboard
- The verification plan (below)

Label unvalidated fixes clearly. One concern per PR — don't bundle unrelated fixes.

## 5. Verify after deploy

Once merged and deployed:
1. Confirm post-fix traffic arrives under the new `service_version`
   (`GET /v1/traces?service_version=<new>&size=5`). For a tool-schema fix, also check
   that the tool definition recorded on that traffic matches the tested schema.
2. Re-run the eval job on fresh traffic and compare the affected scorers before and
   after. If AutoFix is enabled, also run NovaPilot and a new AutoFix run on the
   post-fix traffic (`experiments-autofix.md`) and compare its verdicts with the
   earlier run.
3. Report the outcome to the user either way — including "no measurable change" or
   regressions. The loop is only closed by measurement, not by merging.
