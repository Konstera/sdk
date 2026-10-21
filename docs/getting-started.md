# Getting started: your first Konstera agent

This guide takes you from an empty folder to an agent that runs on a Konstera instance and puts a draft in the reviewer Inbox.

A Konstera agent is a container image. The platform starts the container, sends it HTTP requests, and the agent calls platform services (logs, LLMs, state, approvals, connected systems) back over MCP. The SDK handles both directions for you.

## What you need

| Item | Notes |
|---|---|
| Python 3.11 or later | The Python SDK needs 3.11+. |
| Docker | To build the agent image. |
| A clone of this `sdk` repository | The Dockerfile below builds the SDK wheel from `python/`. |
| A Konstera instance | You need permission to upload and deploy agents, and access to the Inbox. |
| A container registry | One the Konstera instance can pull from. |

## 1. Write the agent

Create a folder `hello-agent/` with a file `main.py`:

```python
from konstera_sdk import Agent, AgentContext, AgentRequest, AgentResponse, run


class HelloAgent(Agent):
    async def handle(self, req: AgentRequest, ctx: AgentContext) -> AgentResponse:
        payload = req.payload or {}

        # A reviewer decided a draft this agent submitted earlier.
        if payload.get("invocation_type") == "on_decision":
            decision = payload.get("decision")
            await ctx.log.info("Decision received", decision=decision,
                               approval_id=payload.get("approval_id"))
            return AgentResponse(content=f"Reviewer chose: {decision}")

        name = req.input.strip() or str(payload.get("name") or "world")
        greeting = f"Hello, {name}!"
        await ctx.log.info(greeting, name=name)

        # Ask a person to review the greeting before it counts.
        if payload.get("review"):
            approval = await ctx.human.request(
                kind="greeting",
                tier="T1",
                summary=f"Greeting for {name}",
                detail={"subject": f"Greeting for {name}", "content_md": greeting},
                invocation_id=req.invocation_id,
            )
            return AgentResponse(
                content=greeting,
                structured={"approval_id": approval.approval_id, "status": approval.status},
            )

        return AgentResponse(content=greeting)


if __name__ == "__main__":
    run(HelloAgent())
```

What the pieces do:

- `Agent.handle()` runs once per invocation. You can also override `initialize()` (once at start-up) and `shutdown()`.
- `AgentRequest` gives you `invocation_id`, `input` (text), `payload` (JSON or `None`) and `config` (the per-agent settings).
- `AgentResponse` returns `content` (text) and, optionally, `structured` (JSON).
- `run()` serves `GET /health`, `GET /describe` and `POST /invoke` on port 8080.
- `ctx.human.request(..., tier="T1")` creates an approval that waits for a person. Pass `invocation_id` so the platform can open an Inbox thread for it.

## 2. Add a Dockerfile

The SDK is built from your clone of this repository. Save this as `hello-agent/Dockerfile`:

```dockerfile
# Stage 1: build the konstera-sdk wheel from your SDK clone
# (passed in as the named build context "sdk").
FROM python:3.13-slim AS build-sdk
RUN pip install --no-cache-dir build
COPY --from=sdk . /sdk-source
WORKDIR /sdk-source
RUN python -m build --wheel --outdir /wheels

# Stage 2: the agent image
FROM python:3.13-slim
RUN groupadd --system agent && useradd --system --gid agent --create-home agent
WORKDIR /app
COPY --from=build-sdk /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY main.py ./
USER agent
EXPOSE 8080
ENTRYPOINT ["python", "-u", "main.py"]
```

## 3. Build and try the image locally

Build from the `hello-agent/` folder. Point `sdk=` at the `python/` folder of your SDK clone:

```bash
docker build -t hello-agent:0.1.0 --build-context sdk=../sdk/python .
```

Run it and call it by hand:

```bash
docker run --rm -p 8080:8080 hello-agent:0.1.0

curl http://localhost:8080/health
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{"invocationId": "local-1", "input": "", "payload": {"name": "Ada"}}'
# {"content":"Hello, Ada!","structured":null,"toolCalls":[]}
```

Outside the platform the agent runs in "direct-run" mode:

- `ctx.log.*` calls are skipped.
- Calls that need a result (`ctx.human`, `ctx.state`, `ctx.llm`, `ctx.capability`, …) raise an error. So `{"review": true}` fails locally; it works once deployed.

## 4. Write the manifest

The manifest tells the platform how to run the agent and what it needs. Save this as `hello-agent/manifest.json`:

```json
{
  "manifestVersion": 3,
  "id": "com.example.hello-agent",
  "name": "Hello Agent",
  "version": "0.1.0",
  "description": "Says hello. Can ask a reviewer to approve the greeting.",
  "icon": "👋",
  "groupName": "Examples",

  "runtime": {
    "kind": "container",
    "image": "registry.example.com/hello-agent:0.1.0",
    "port": 8080,
    "healthPath": "/health",
    "timeoutSeconds": 30
  },

  "kernelServices": {
    "required": ["log", "human"]
  }
}
```

- `id` is reverse-DNS and lower case. `version` is SemVer.
- `runtime.image` must be the image reference the platform pulls (step 6).
- `runtime.port` and `runtime.healthPath` must match the image: the SDK uses `8080` and `/health`.

See the [manifest reference](manifest-reference.md) for every field.

## 5. Validate the manifest locally

The schema is `schemas/agent-manifest.v3.json` in this repository. Check your manifest before you upload it:

```bash
pip install jsonschema
```

```python
# validate_manifest.py
import json
import sys

from jsonschema import Draft202012Validator

schema = json.load(open(sys.argv[1], encoding="utf-8"))
manifest = json.load(open(sys.argv[2], encoding="utf-8"))
errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: list(e.path))
for e in errors:
    print("/".join(map(str, e.path)) or "(root)", ":", e.message)
print("valid" if not errors else f"{len(errors)} error(s)")
sys.exit(1 if errors else 0)
```

```bash
python validate_manifest.py ../sdk/schemas/agent-manifest.v3.json manifest.json
```

The platform runs the same schema at upload, plus a few extra checks the schema cannot express (see [manifest reference](manifest-reference.md#checks-beyond-the-schema)).

## 6. Make the image reachable

The platform pulls `runtime.image` when it starts the agent. Push the image to a registry the instance can pull from:

```bash
docker tag hello-agent:0.1.0 registry.example.com/hello-agent:0.1.0
docker push registry.example.com/hello-agent:0.1.0
```

Ask your Konstera administrator which registry to use and whether it needs pull credentials. Use a fixed tag per version; do not reuse a tag for different code.

## 7. Upload the manifest

1. In the portal, open **Agents › Catalog**.
2. Drop `manifest.json` on the upload area (**Drop an agent manifest (.json)**), or click it to pick the file.
3. If the upload is rejected, the **Upload rejected** message lists each failing field path. Fix it and upload again.

Uploading the same `id` and `version` again replaces that version's manifest.

## 8. Deploy

1. In the Catalog row for your agent, click **Deploy**.
2. Pick the **Version**, enter an **Instance name** and click **Deploy**.
3. You land on the new agent's page. It has these tabs: **Overview**, **Runs**, **Triggers**, **Bindings**, **Test**, **Access**, **Technical details**.

A new agent starts in the stopped state. You can deploy the same package more than once, under different names.

## 9. Bind what the agent needs

Open the **Bindings** tab. It shows only what your manifest declares:

| Section | Comes from | What you do |
|---|---|---|
| **Connections this agent uses** | `capabilities.needs` | Read-only summary. Flags required capabilities that have no connection yet. |
| **Step 1 · Models** | `llmRequirements` | Pick a model per purpose, or keep the tenant default. |
| **Step 2 · Data & tools** | `capabilities.needs` | Bind each capability to a connection. |
| **Action targets** | `reviewActions` with `actionType` `email`, `webhook` or `api` | Bind each target slot to a connection. |
| **Step 3 · Instance configuration** | `config` | Fill in the settings form. |

The hello agent declares none of these, so there is nothing to bind yet.

## 10. Start and test

1. Click **Start agent** at the top of the page. The platform pulls the image and starts it.
2. Open the **Test** tab.
3. In **Payload (JSON)**, enter a payload and click **Run**:

```json
{ "name": "Ada" }
```

The Test tab sends what you type as the request **payload**. `req.input` is empty for Test runs, so read your test values from `req.payload`.

The run also appears on the **Runs** tab, marked as a test.

## 11. See a draft in the Inbox

Run the Test tab again with:

```json
{ "name": "Ada", "review": true }
```

The agent calls `ctx.human.request(tier="T1", ...)`. The platform:

1. Stores a pending approval.
2. Opens a thread in **Inbox**. The draft text is `detail.content_md`; the thread subject is `detail.subject`.

Open **Inbox**, pick the thread and choose an action. The platform then invokes your agent again with a payload like this:

```json
{
  "invocation_type": "on_decision",
  "approval_id": "…",
  "decision": "approve",
  "reason": null,
  "actor_id": "…",
  "actor_role": "…",
  "inputs": {}
}
```

The agent's `on_decision` branch handles it. That run appears on the **Runs** tab.

## Next steps

- [Manifest reference](manifest-reference.md): capabilities, models, settings, Inbox buttons and context panels.
- [Agent FAQ](faq-agents.md): common questions from agent authors.
- [Review actions demo](examples/review-actions-demo/): a small agent that uses every Inbox action type.
