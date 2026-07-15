# Integrating Assemblix workflow execution

How to call a **published** Assemblix workflow from your own product (backend or
frontend): trigger a run, wait or poll for the result, stream tokens live, keep a
stateful chat session, and send voice. This is the reference for wiring Assemblix
into an application — not for authoring the graph (for that, use the workflow tools
and the example resources).

> Source of truth: this mirrors the public docs page `docs/workflows/execute.md`.
> `BASE` below is your instance base URL (the same `ASSEMBLIX_API_URL` the MCP uses,
> e.g. `https://app.assmblx.com`). Auth is the same project `sk_` key.

## 1. Trigger a run

```
POST {BASE}/api/workflows/{workflowId}/execute
```

`{workflowId}` is the workflow UUID (from the editor URL or the workflows list). The
run executes the **published** snapshot, so publish the workflow first.

**Auth** — Bearer `sk_` key on every request:

```
Authorization: Bearer sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

A missing/invalid key → `401`. The key is project-scoped: it can run any workflow in
its project. `projectId` is never sent — the server derives it from the key.

### Request body (JSON)

Only `input` is required; everything else is optional.

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `input` | object | *(required)* | Payload for the START node. Chat workflows read `input.message`. |
| `sessionId` | uuid | `null` | Continue an existing chat session (history + state carry over). |
| `createSession` | bool | `false` | Start a NEW session and return its id. Mutually exclusive with `sessionId`. |
| `sessionName` | string | `null` | Label applied when a session is created. |
| `state` | object | `null` | Seed run state variables (merged over workflow defaults; yours win). |
| `projectState` | object | `null` | Seed project-level state (shared across the project's workflows). |
| `task` | bool | `false` | Return an `executionId` immediately instead of waiting. See §3. |
| `stream` | bool | `false` | Publish token deltas over SSE. See §4. |
| `clientId` | string | `null` | Your end-user identifier; ties state across workflows. |
| `metadata` | object | `null` | Arbitrary key/values stored on the session. |

## 2. Run and get the answer (synchronous)

The simplest call sends a message and waits for the reply.

**cURL**
```bash
curl -X POST {BASE}/api/workflows/{workflowId}/execute \
  -H "Authorization: Bearer sk_..." \
  -H "Content-Type: application/json" \
  -d '{ "input": { "message": "Hi there" } }'
```

**JavaScript**
```js
const res = await fetch(`${BASE}/api/workflows/${workflowId}/execute`, {
  method: "POST",
  headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
  body: JSON.stringify({ input: { message: "Hi there" } }),
});
const run = await res.json();
console.log(run.output.message);
```

**Python**
```python
import requests
res = requests.post(
    f"{BASE}/api/workflows/{workflow_id}/execute",
    headers={"Authorization": f"Bearer {key}"},
    json={"input": {"message": "Hi there"}},
)
print(res.json()["output"]["message"])
```

### Success response (`ExecutionResponse`)

```json
{
  "executionId": "3f1c2b6a-…",
  "sessionId": null,
  "status": "completed",
  "output": { "message": "Hello!", "parsed_message": null, "tool_executions": [] },
  "state": {},
  "projectState": {},
  "metadata": { "totalSteps": 3, "durationMs": 1240, "creditsUsed": 2.5, "ownKeyCostUsd": null },
  "isSessionClosed": false
}
```

- `output.message` — the reply text from the END node.
- `output.parsed_message` — parsed object when the agent used a JSON response format, else `null`.
- `output.audio` — present when an agent node has `outputType: "voice"` (see §6).
- `executionId` — use it to fetch step detail or subscribe to the stream.

### Error response (`ExecutionErrorResponse`)

Always check `status` before reading `output`:

```json
{
  "executionId": "3f1c2b6a-…",
  "status": "failed",
  "error": "Agent request timed out",
  "errorType": "node_error",
  "failedNodeId": "agent-1",
  "partialState": {},
  "partialProjectState": {}
}
```

`errorType` ∈ e.g. `node_error`, `timeout`, `runtime`. `failedNodeId` points at the broken node.

## 3. Async (`task: true`) + polling

For slow workflows, pass `task: true` to get an id immediately:

```json
POST body: { "input": { "message": "Hi" }, "task": true }
→ { "executionId": "3f1c2b6a-…", "status": "running" }
```

Then poll the **task endpoint** until `status != "running"`. IMPORTANT — the poll path
is under `/api/workflows/`, NOT `/api/executions/`:

```
GET {BASE}/api/workflows/task/{executionId}
```

While running it returns `{"status": "running"}`; when done, the **same** endpoint
returns the full `ExecutionResponse` (or the failed shape).

**JavaScript**
```js
async function waitForResult(executionId) {
  for (;;) {
    const res = await fetch(`${BASE}/api/workflows/task/${executionId}`, {
      headers: { Authorization: `Bearer ${key}` },
    });
    const run = await res.json();
    if (run.status !== "running") return run;
    await new Promise((r) => setTimeout(r, 1000));
  }
}
```

**Python**
```python
import time, requests
def wait_for_result(execution_id):
    while True:
        run = requests.get(
            f"{BASE}/api/workflows/task/{execution_id}",
            headers={"Authorization": f"Bearer {key}"},
        ).json()
        if run["status"] != "running":
            return run
        time.sleep(1)
```

Note: even a synchronous (`task:false`) call falls back to async automatically if it
exceeds `TASK_TIMEOUT_SECONDS` — it then returns just `{executionId, status:"running"}`,
so a robust client always handles the "running → poll" path. With the Arq worker tier
(`EXECUTION_QUEUE_ENABLED=true`) the request/response shapes are unchanged.

## 4. Streaming (token-by-token, SSE)

`stream: true` does NOT change the execute response — it turns on a **Server-Sent
Events** side channel you subscribe to with the `executionId`:

```
GET {BASE}/api/executions/{executionId}/stream
Accept: text/event-stream
```

(Note this one IS under `/api/executions/`.) Typical flow: `POST /execute` with
`{ "input": {...}, "stream": true, "task": true }`, take the `executionId`, then open
the stream.

**cURL**
```bash
curl -N {BASE}/api/executions/{executionId}/stream \
  -H "Authorization: Bearer sk_..." -H "Accept: text/event-stream"
```

**JavaScript (browser EventSource)**
```js
const es = new EventSource(`${BASE}/api/executions/${executionId}/stream`);
es.addEventListener("stream_delta", (e) => {
  const { data } = JSON.parse(e.data);
  appendToUI(data.delta);            // each token chunk
});
es.addEventListener("execution_complete", () => es.close());
```

**Python**
```python
import json, requests
with requests.get(
    f"{BASE}/api/executions/{execution_id}/stream",
    headers={"Authorization": f"Bearer {key}", "Accept": "text/event-stream"},
    stream=True,
) as res:
    for line in res.iter_lines():
        if line and line.startswith(b"data:"):
            event = json.loads(line[5:])
            if event["eventType"] == "stream_delta":
                print(event["data"]["delta"], end="", flush=True)
```

Key facts:
- Each frame carries a monotonically increasing `seq`. Send it back as a
  `Last-Event-ID` header (or `?cursor=<seq>`) to **resume** after a dropped connection —
  the server replays from that cursor, then tails live.
- Text tokens arrive as `stream_delta` events; the run ends with `execution_complete`.
  Event types match debug mode.
- The stream endpoint `404`s if there is no live buffer (a non-streaming run, or it
  expired). Fall back to `GET /api/workflows/task/{executionId}` for the final result.
- The buffer opens shortly after a `task:true` run returns its id — the server waits up
  to ~10s for it, so subscribe promptly.

## 5. Chat sessions (stateful)

By default each run is one-shot. Pass `createSession: true` on the first turn to get a
`sessionId` back, then pass that `sessionId` on every subsequent turn — history and
state persist within the session, so turns build on each other. The START node's
`firstPhrase` seeds the first assistant message when a session is created.
`isSessionClosed: true` in a response means an END node closed the session.

## 6. Voice

**Voice input** — `multipart/form-data` to a dedicated endpoint (the START node must
have `acceptVoice` enabled, else `400`):

```
POST {BASE}/api/workflows/{workflowId}/execute/audio
```
Parts: `file` (the audio blob, e.g. `.mp3`/`.wav`/`.webm`; transcribed by Whisper) and
`payload` (a JSON **string** of the same body as the text route — `input`, `sessionId`,
`task`, `stream`, …; optional, defaults to `{}`). The transcript is placed into
`input.message`; the response is the same `ExecutionResponse`.

```bash
curl -X POST {BASE}/api/workflows/{workflowId}/execute/audio \
  -H "Authorization: Bearer sk_..." \
  -F "file=@question.mp3;type=audio/mpeg" \
  -F 'payload={"createSession": true}'
```

**Voice output** — give an AGENT node `outputType: "voice"`. Non-streaming: the reply
audio is returned inline on `output.audio` (`{ base64, format, voiceId, model }`) —
decode `base64` (mp3) to play. Real-time: set the agent's `voice.realtime = true` and
run with `stream: true`; subscribe to the SSE stream and read **`audio_delta`** events
(base64 PCM chunks, `format` `pcm_16000`, optional character `alignment` for lip-sync).

**Avatars** — `outputType: "avatar"` reuses the agent's streamed output to drive a
talking avatar; run with `stream: true` and subscribe to the SSE stream.

## Quick decision guide

- Simple request/response → §2 (sync).
- Might be slow / want to not hold a connection → §3 (`task:true` + poll `/api/workflows/task/{id}`).
- Live typing effect / long answers → §4 (`stream:true` + SSE `/api/executions/{id}/stream`).
- Multi-turn conversation → §5 (`createSession` then reuse `sessionId`).
- Speech in/out → §6.
