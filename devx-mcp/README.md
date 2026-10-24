# Konstera DevX MCP

MCP server that exposes Konstera's **capability catalogue** as tools your
coding agent can call. Instead of pasting the whole catalogue into the chat
every time you ask Claude Code / Cursor / Windsurf "which capability does
X?", the agent discovers it inline through MCP.

Three tools:

| Tool | Returns |
|---|---|
| `catalogue_list_capabilities(category?)` | Every canonical capability key, optionally filtered by category |
| `catalogue_get_capability(key)` | Full detail: arg schema, response shape, effect, fanout, cache TTL |
| `catalogue_search(query)` | Freetext search ranked by key > display_name > category > description hits |

The data behind these tools is a vendored snapshot of
`sdk/schemas/capability-catalog.json` — the same file every language SDK
ships. Updated at package build time (`npm run build`), so a published
version carries exactly the catalogue that was canonical when it was cut.

## Install

### Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "konstera-devx": {
      "command": "npx",
      "args": ["-y", "@konstera/devx-mcp"]
    }
  }
}
```

Then restart Claude Desktop. The tools appear under the hammer icon.

### Cursor

Add to `.cursor/mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "konstera-devx": {
      "command": "npx",
      "args": ["-y", "@konstera/devx-mcp"]
    }
  }
}
```

Reload Cursor. Tools are callable from Composer / Cmd+K.

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "konstera-devx": {
      "command": "npx",
      "args": ["-y", "@konstera/devx-mcp"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add konstera-devx -- npx -y @konstera/devx-mcp
```

## Usage patterns

**Before writing a `ctx.capability.call(...)` line:**

> "Which capability lists tickets that need my team's reply?"

The agent calls `catalogue_search(query="tickets unresolved")` and finds
`tickets.list_unresolved` without you having to remember the exact key.

**When you know roughly what you want:**

> "What are the orders capabilities?"

Agent calls `catalogue_list_capabilities(category="orders")` and lists them.

**When you need the exact shape:**

> "Show me the schema for orders.lookup_by_email."

Agent calls `catalogue_get_capability(key="orders.lookup_by_email")` and
shows arg schema + response shape so the agent can code against them.

## Local development

```bash
npm install
npm run build        # copies the catalogue + compiles TypeScript
npm test             # vitest smoke tests
npm start            # starts the MCP server over stdio for local inspection
```

Point your IDE / Claude Desktop at the local dist/ instead of the
published package while iterating:

```json
{
  "mcpServers": {
    "konstera-devx-local": {
      "command": "node",
      "args": ["/absolute/path/to/sdk/devx-mcp/dist/bin.js"]
    }
  }
}
```

## Scope

**v1 is read-only — catalogue tools only.** Write capabilities (register a
custom MCP endpoint, propose a new capability key, lint a manifest against
the catalogue) are planned for v2 (`devx-mcp-v2` on the backlog).

License: Apache-2.0.
