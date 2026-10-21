# Konstera developer docs

Public documentation for developers who build agents to run on Konstera.

**Audience:** agent authors. Not platform engineers, and not operators who install Konstera.

## Pages

| Page | What it covers |
|---|---|
| [Getting started](getting-started.md) | Write a Python agent, build the image, write and validate a manifest, upload, deploy, bind, test, and see a draft in the Inbox. |
| [Manifest reference](manifest-reference.md) | Every section of `agent-manifest.v3.json`, with examples and where each shows up in the portal. |
| [Agent FAQ](faq-agents.md) | Common questions: LLM and capability calls, Inbox buttons, decisions, context panels, versions, testing, data. |
| [Review actions demo](examples/review-actions-demo/) | A demo agent (made-up data) that uses every Inbox action type. |

The manifest schema is [`schemas/agent-manifest.v3.json`](../schemas/agent-manifest.v3.json).

## Planned pages

- `concepts.md` — what an agent is, how invocations work, platform services (MCP), tenants
- `sdk-reference-dotnet.md` — `Agent`, `AgentContext`, platform service clients
- `sdk-reference-python.md` — same, Pythonic surface
- `mcp-callbacks.md` — what the platform exposes over MCP (`llm`, `vector`, `state`, `credentials`, `cost`, `log`, `tool`, `agents`, `human`, `capability`, …)
- `cli-reference.md`, `local-dev.md`, `cli-sdk-compatibility.md` — once the CLI ships
- `eval-guide.md`, `ci-cd.md`, `cookbook/` — later
