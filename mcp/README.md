# assemblix-mcp

MCP server for [Assemblix](https://app.assmblx.com). Author, run & inspect your
project's workflows from any MCP client using a single project API key (`sk_...`).
`projectId` is never needed — the key defines the project.

Get your `sk_` key from the project's **API keys** page in the Assemblix UI.

## Install

### Hosted (easiest — nothing to install)

```
claude mcp add --transport http assemblix https://mcp.assmblx.com \
  --header "Authorization: Bearer sk_your_key"
```

### Local via uvx (privacy / self-host)

```
claude mcp add assemblix \
  --env ASSEMBLIX_API_KEY=sk_your_key \
  --env ASSEMBLIX_API_URL=https://app.assmblx.com \
  -- uvx assemblix-mcp
```

### Claude Desktop / Cursor (JSON config)

```json
{
  "mcpServers": {
    "assemblix": {
      "command": "uvx",
      "args": ["assemblix-mcp"],
      "env": {
        "ASSEMBLIX_API_KEY": "sk_your_key",
        "ASSEMBLIX_API_URL": "https://app.assmblx.com"
      }
    }
  }
}
```

For the hosted server, use your client's "add custom connector → URL + header" flow.

## Configuration

| Env var | Default | Notes |
| --- | --- | --- |
| `ASSEMBLIX_API_URL` | `https://app.assmblx.com` | Base URL of your Assemblix instance |
| `ASSEMBLIX_API_KEY` | — | Project `sk_` key. Required for stdio; for hosted HTTP the `Authorization` header is used instead |
| `ASSEMBLIX_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `ASSEMBLIX_MCP_HOST` / `ASSEMBLIX_MCP_PORT` | `0.0.0.0` / `8000` | HTTP transport bind |

## Tools

**Workflow authoring:** `list_node_types`, `list_workflows`, `get_workflow`,
`create_workflow`, `update_workflow`, `publish_workflow`
**Run & inspect:** `run_workflow`, `run_workflow_and_wait`, `get_execution`,
`list_executions`, `get_execution_detail`, `list_in_flight`
**Voice agents:** `list_conversation_voices`, `list_voice_agents`, `get_voice_agent`,
`create_voice_agent`, `update_voice_agent`, `delete_voice_agent`, `list_voice_calls`,
`get_voice_call`

**Resources:** `assemblix://examples/minimal`, `assemblix://examples/branching`
(example workflow JSON), `assemblix://guides/execution` (how to call a workflow from
your product — sync/async/streaming/sessions/voice, with curl/JS/Python examples),
`assemblix://guides/voice-agents` (what a voice agent is, the call WebSocket protocol,
analysis hooks, reading calls back).
**Prompts:** `author_workflow`, `integrate_workflow`, `integrate_voice_agent`.

Workflow lifecycle: `create_workflow → update_workflow(nodes, edges) →
publish_workflow → run_workflow`. Runs always execute the **published** snapshot.
AGENT nodes need a provider credential configured in the Assemblix UI.

A **voice agent** is a different thing: no graph, no publish step — a prompt plus a
speech-to-speech voice, answering a live call. Workflows attach to it only as
background analysis. Build one with `list_conversation_voices → create_voice_agent`,
then iterate on real calls with `list_voice_calls` / `get_voice_call`.

All tools operate on the single project your API key is scoped to; `projectId` is
never a parameter.
