# claude-skills

Standalone [Claude Code Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
for working with Noveum — each a self-contained `SKILL.md` (some with helper `scripts/`).
Unlike the top-level [`noveum-ai/`](../noveum-ai) skill (the packaged, end-to-end reliability
engineer), these are **focused, à-la-carte tools** you can drop into `~/.claude/skills/`
(personal) or a project's `.claude/skills/` individually.

The NovaSynth capabilities here are also integrated into the main `noveum-ai` skill as
references — see `noveum-ai/references/novasynth-*.md`. These standalone copies stay useful
on their own, outside the full journey.

| Skill | What it does |
|---|---|
| `novasynth-run/` | Orchestrate a NovaSynth synthetic-testing run end-to-end as human-in-the-loop checkpoints: inputs → run calls → per-call audit → report. |
| `novasynth-assist/` | Validate scenarios, and audit a batch run — transcripts against the spec + cross-check the platform scorers (their known false-passes/false-fails). |
| `novapilot-audit/` | Audit a NovaPilot report JSON: are its recommendations, item attributions, and fixes actually trustworthy? |
| `noveum-dataset/` | Download/upload Noveum datasets, items, scorer results, and audio via the REST API (self-contained Python scripts). |
| `novaeval-scorer/` | **Internal / contributor tooling** — add & register a new scorer inside the NovaEval source repo. Requires a NovaEval checkout; not a platform/API skill. |

## Auth

The **platform-facing** skills — `novasynth-run`, `novasynth-assist`, `novapilot-audit`,
`noveum-dataset` — talk to the Noveum REST API (`https://api.noveum.ai/api/v1`) or the
`noveum` MCP server. Credential precedence (highest first):

1. an explicit `--api-key` flag (the `noveum-dataset` scripts),
2. `NOVEUM_API_KEY` in the environment or a local `.env`,
3. a project-scoped `<PROJECT>_NOVEUM_API_KEY` for multi-project setups.

`novasynth-assist` can additionally read the key from the `noveum` MCP config in
`~/.claude.json`. **Never hardcode a key in these files.**

`novaeval-scorer` is **not** platform-facing — it edits the NovaEval source repo and needs a
key only for the optional audio-fetch endpoint (`NOVEUM_API_KEY` or `EXOTEL_API_KEY`).
