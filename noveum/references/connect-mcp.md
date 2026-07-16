# Connect to the Noveum MCP server

The hosted MCP server exposes the full platform surface: ~60 tools generated from the
live API, 16 read-first `noveum://` resources, and 20 workflow prompts. Prefer it over
raw REST — schemas are always current and the workflow prompts encode the same
procedures as this skill.

Endpoint: `https://noveum.ai/api/mcp` (streamable HTTP).

## Two auth modes — pick by client type

**OAuth 2.1 (URL-only clients — the default for interactive use).** Cursor, Claude &
Claude Code, VS Code, ChatGPT (developer mode), Windsurf, Cline, Replit, Zed, Goose, and
any client implementing the MCP authorization spec: add just the URL. The client
discovers OAuth automatically (an unauthenticated request returns 401 with
`WWW-Authenticate` pointing at `/.well-known/oauth-protected-resource`), registers itself
(dynamic client registration), and opens a Noveum sign-in + consent screen — no key, no
manual OAuth-app setup. Notes:
- The token is bound to **one organization**, chosen on the consent screen. To work
  against a different org, run the connect flow again.
- Scopes (`noveum.read`, `noveum.write`, `noveum.execute`) are chosen at consent and only
  narrow access; org RBAC still applies on top.

**Bearer API key (headless / scripted clients).** Same key as REST:

```bash
claude mcp add --transport http noveum https://noveum.ai/api/mcp \
  --header "Authorization: Bearer ${NOVEUM_API_KEY}"
```

Generic `mcp.json` (see `assets/mcp.json.template`):

```json
{ "mcpServers": { "noveum": {
    "url": "https://noveum.ai/api/mcp",
    "headers": { "Authorization": "Bearer ${NOVEUM_API_KEY}" } } } }
```

## Local variant for large payloads

`@noveum/mcp-local` (npm) is a stdio MCP server that mirrors the hosted tool surface but
streams large responses (full datasets, reports) to local files, returning
`{ savedTo, bytes, sha256 }` instead of flooding context. Prefer it when pulling dataset
items or full reports; if it isn't available on the org yet, use the hosted server and
page through results.

## Usage rules

- Reference tools fully qualified (`noveum:<tool_name>`) to avoid tool-not-found errors
  when multiple MCP servers are connected.
- Read `noveum://projects`, `noveum://filter-values`, and `noveum://org-status` before
  querying traces — never invent ids or slugs.
- Long-running work is queued: kick off, then poll the matching status tool until a
  terminal status (cadence table in [api-reference.md](api-reference.md)).
- The server's `full_agent_improvement_cycle` prompt walks the same journey as this
  skill; if the live server and this skill disagree, the live server wins.
