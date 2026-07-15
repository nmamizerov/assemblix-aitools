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

**Authoring:** `list_node_types`, `list_workflows`, `get_workflow`, `create_workflow`,
`update_workflow`, `publish_workflow`
**Run & inspect:** `run_workflow`, `run_workflow_and_wait`, `get_execution`,
`list_executions`, `get_execution_detail`, `list_in_flight`

**Resources:** `assemblix://examples/minimal`, `assemblix://examples/branching`
(example workflow JSON), `assemblix://guides/execution` (how to call a workflow from
your product — sync/async/streaming/sessions/voice, with curl/JS/Python examples).
**Prompts:** `author_workflow` (authoring guide), `integrate_workflow` (integration guide).

Lifecycle: `create_workflow → update_workflow(nodes, edges) → publish_workflow →
run_workflow`. Runs always execute the **published** snapshot. AGENT nodes need a
provider credential configured in the Assemblix UI.

All tools operate on the single project your API key is scoped to; `projectId` is
never a parameter.
