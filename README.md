# Noveum Agent Skill

The official [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
for [Noveum.ai](https://noveum.ai) — give your coding agent everything it needs to set up
and operate Noveum **end to end, inside your own environment**:

1. Integrate the `noveum-trace` SDK (LangChain/LangGraph, CrewAI, LiveKit, Pipecat, or manual)
2. **Verify the integration** — a trace-completeness report card, not just "it compiled"
3. Build eval datasets from real traffic
4. Select scorers and run evaluations
5. Diagnose failures with NovaPilot
6. Backtest fixes with AutoFix experiments
7. Apply validated fixes and verify them in production

Works with Claude Code, Claude (Enterprise/Team skills), the Claude Agent SDK, and any
agent that reads `SKILL.md`-style instructions.

## Data flow (for your security review)

**Your code never leaves your environment.** The skill runs inside *your* agent with
*your* credentials. The only data sent to Noveum is telemetry (traces/spans) emitted by
the `noveum-trace` SDK over HTTPS with your org-scoped API key — the same data flow you
opt into by using the SDK at all. The skill contains no telemetry of its own, no external
dependencies, and two small stdlib-only Python scripts you can read in one sitting
(`noveum/scripts/`). The API key is only ever read from the `NOVEUM_API_KEY` environment
variable.

## Install

**Claude Code (project-level, recommended for teams — reviewable in your own PR):**

```bash
git clone https://github.com/Noveum/noveum-skill /tmp/noveum-skill
mkdir -p .claude/skills
cp -r /tmp/noveum-skill/noveum .claude/skills/noveum
```

**Claude Code (personal):** copy `noveum/` to `~/.claude/skills/noveum`.

**Claude Enterprise/Team:** an admin can upload the `noveum/` folder as an organization
skill so every seat gets it with zero setup.

**Any other agent (Cursor, Codex, Copilot, …):** point it at
[`noveum/SKILL.md`](noveum/SKILL.md), or use the same instructions rendered at
[noveum.ai/agents.md](https://noveum.ai/agents.md).

Then just ask your agent: *"Integrate Noveum into this repo and verify traces are
flowing."*

## What's inside

```
noveum/
├── SKILL.md                     # the journey: 7 steps, each with an acceptance check
├── references/                  # loaded on demand (progressive disclosure)
│   ├── integrate-langchain.md   #   + crewai, livekit, pipecat, openai-manual
│   ├── verify-traces.md         # the completeness report card (step-1 gate)
│   ├── setup-evals.md           # datasets → ETL → scorers → eval runs
│   ├── diagnose-novapilot.md    # diagnosis reports
│   ├── experiments-autofix.md   # backtested fixes & experiments
│   ├── apply-fixes.md           # fix → repo edit → PR → verify
│   ├── connect-mcp.md           # hosted MCP server (OAuth 2.1 or API key)
│   ├── api-reference.md         # endpoints, polling contract, credits
│   └── troubleshooting.md
├── scripts/
│   ├── send_test_trace.py       # prove connectivity with one known-good trace
│   └── check_integration.py     # the trace-completeness report card
└── assets/
    └── mcp.json.template
```

## Versioning & updates

Semver via git tags + [CHANGELOG.md](CHANGELOG.md). The skill keeps durable procedures
local and fetches volatile detail (exact API schemas) from live surfaces at run time, so
a vendored copy ages gracefully — but do pull updates occasionally.

## Requirements

- A Noveum account, API key, and org slug (dashboard → Settings → API Keys)
- Python ≥ 3.9 in the target repo for the SDK (`pip install noveum-trace`)
- No dependencies for the skill's own scripts (stdlib only)

## License

MIT — see [LICENSE](LICENSE).
