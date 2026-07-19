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

**Event envelope** — every frame is JSON, **snake_case**:
```json
{ "event_type": "stream_delta", "data": { "node_id": "...", "step_number": 3, "delta": "Hel" }, "seq": 12 }
```
- `event_type` — `stream_delta` (text token) · `audio_delta` (voice chunk) ·
  `execution_complete` (final) · node lifecycle (`step_start`/`step_complete`).
- `data` always has `node_id` + `step_number`, plus the payload: `delta` (text) OR
  `audio` (base64) + `format` + `alignment` (voice). Audio is in **`data.audio`**, not `data.base64`.
- `seq` — monotonic; send back as `Last-Event-ID` (or `?cursor=<seq>`) to resume **while
  the buffer is still live**.

**JavaScript (browser EventSource)**
```js
const es = new EventSource(`${BASE}/api/executions/${executionId}/stream`);
es.addEventListener("stream_delta", (e) => {
  const { data } = JSON.parse(e.data);
  appendToUI(data.delta);                 // each text token chunk
});
es.addEventListener("audio_delta", (e) => {
  const { data } = JSON.parse(e.data);
  playPcm(data.audio, data.format);       // base64 PCM in data.audio (pcm_16000)
});
es.addEventListener("execution_complete", (e) => {
  const { data } = JSON.parse(e.data);    // status, output.message, final_state, session_id, is_session_closed
  es.close();
});
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
            if event["event_type"] == "stream_delta":     # snake_case
                print(event["data"]["delta"], end="", flush=True)
```

Key facts:
- **Streaming needs `task: true`.** A plain `/execute` (or `/execute/audio`) blocks until
  the run finishes, so by the time you hold the `executionId` the buffer is already gone.
  Always start streaming runs async, then subscribe.
- **`execution_complete` carries the whole final result** in `data` (`status`,
  `output.message`, `final_state`, `session_id`, `is_session_closed`) — it is the reliable
  way to get the answer over SSE.
- The buffer is **short-lived**: it opens ~10s after a `task:true` run returns its id
  (subscribe promptly) and is **discarded when the run ends** — a re-subscribe afterwards
  `404`s `"No active stream"`. `Last-Event-ID` replays only within the live buffer, not
  from a durable store.
- If the stream `404`s (non-streaming or expired), fall back to
  `GET /api/workflows/task/{executionId}`. ⚠️ For an error-END with a custom message this
  endpoint currently reports a generic `status: "failed"` / `"Unknown error"` and drops
  the custom text — sync `/execute` and SSE return the correct `status: "error"` + message.

## 5. Chat sessions (stateful)

By default each run is one-shot. Pass `createSession: true` on the first turn to get a
`sessionId` back, then pass that `sessionId` on every subsequent turn — history and
state persist within the session, so turns build on each other. The START node's
`firstPhrase` seeds the first assistant message when a session is created.
`isSessionClosed: true` in a response means an END node closed the session.

## 6. Voice

**Voice input — two ways to send the audio.** Either upload it as multipart to the audio
endpoint, or embed it as base64 in the normal JSON `/execute` body. Both make the audio the
run's input; any multimodal agent then receives it directly. The START node must have
`acceptVoice: true` (else `400`). START does NOT transcribe — it just gates and passes the
raw audio into the run.

### 6.1 Multipart upload (best for large files)

```
POST {BASE}/api/workflows/{workflowId}/execute/audio
```
`multipart/form-data`, two parts:
- `file` — the audio blob (**WAV** or **MP3**; see format note).
- `payload` — a JSON **string** of the same body as the text route (`input`, `sessionId`,
  `task`, `stream`, …). **Not optional:** it must contain an `input` key — send at least
  `{"input": {}}`, or the call `400`s `Invalid execute payload`.

```bash
curl -X POST {BASE}/api/workflows/{workflowId}/execute/audio \
  -H "Authorization: Bearer sk_..." \
  -F "file=@question.wav;type=audio/wav" \
  -F 'payload={"input": {}, "createSession": true}'
```

### 6.2 base64 in the JSON body (no multipart)

Send the audio as base64 on the **plain** `/execute` (or `/execute/debug`) route — handy for
clients that only speak JSON (front-end, MCP-driven flows). Add these top-level fields
alongside `input`:

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `audioBase64` | string | `null` | The audio blob, base64-encoded. Presence marks the run as an audio turn. |
| `audioMime` | string | `audio/wav` | MIME of the decoded audio (e.g. `audio/wav`, `audio/mpeg`). |
| `audioFilename` | string | `voice.wav` | Optional original filename. |

```bash
curl -X POST {BASE}/api/workflows/{workflowId}/execute \
  -H "Authorization: Bearer sk_..." -H "Content-Type: application/json" \
  -d '{ "input": {}, "createSession": true,
        "audioBase64": "UklGR... (base64)", "audioMime": "audio/wav" }'
```

```python
import base64, requests
audio = base64.b64encode(open("question.wav", "rb").read()).decode()
res = requests.post(
    f"{BASE}/api/workflows/{workflow_id}/execute",
    headers={"Authorization": f"Bearer {key}"},
    json={"input": {}, "audioBase64": audio, "audioMime": "audio/wav"},
)
print(res.json()["output"]["message"])
```

The size cap (`voiceMaxUploadBytes`) applies to the **decoded** bytes; invalid base64 →
`400`, oversized audio → `413`, a START without `acceptVoice` → `400` — same contract as the
multipart route. base64 inflates the payload ~33%, so prefer multipart for large recordings.
Audio runs are always synchronous (they can't be queued), the same as the multipart route.

### 6.3 What the run sees, and how the audio reaches an agent

Both routes load the audio identically: `input.message` is empty,
`input.input_type = "audio"`, and the audio rides on the run for agents to consume (text
runs get `input_type = "text"`). Branch on `input.input_type` in CONDITION CEL. The audio
reaches an agent two ways:

1. **Straight into a multimodal agent (the simple path).** If the agent's model accepts
   audio natively — any model flagged `acceptsAudio` in `list_node_types` — it understands
   the audio as-is: no transcribe node, one fewer round-trip. Two provider families qualify:
   - **Gemini** (`gemini-2.5-*`, `gemini-3-*`, `gemini-3.1-*`, `gemini-3.5-flash`) —
     multimodal both ways: the same agent handles text turns AND audio turns.
   - **OpenAI `gpt-audio` / `gpt-audio-mini`** — audio-in, text-out. ⚠️ **Audio-only:** these
     models *require* audio in the request and will `400`
     (`This model requires that either input content or output modality contain audio`) on a
     plain text turn. Use `gpt-audio` only in an agent that always receives audio — set that
     agent's `audioInput: "audio"` and feed it a real audio turn (do NOT put a `transcribe`
     node before it, which would strip the audio to text). For an agent that must handle both
     text and audio, use Gemini instead.

   (Optional agent field `audioInput`: `"auto"` default = audio if the model accepts it, else
   text · `"audio"` strict · `"text"` strict. A non-audio model that receives audio errors
   with an actionable message.)

2. **Transcribe node → text (for non-audio models / conditions / history).** Place an
   explicit `transcribe` node; it runs STT and turns the audio into text — after it,
   `input.message` is the transcript and `input.input_type` is `"text"`, so downstream
   agents (incl. OpenAI/DeepSeek) get plain text. `voiceModel`
   (`{provider, model, credentialId}`) lives on THIS node now (START no longer has it).
   `saveAsUserMessage` (default `true`) writes the transcript as the user turn in chat
   history, and the same-run downstream agent sees it as the user message.

   ```json
   { "id": "stt-1", "type": "transcribe",
     "config": { "voiceModel": { "provider": "openai", "model": "gpt-4o-transcribe" },
                 "saveAsUserMessage": true } }
   ```

> **Format.** Send a complete-header container — **WAV** or **MP3**. Gemini (audio-direct)
> accepts wav/mp3/ogg/flac/aiff/aac but **not** webm; `gpt-4o-transcribe` rejects
> incomplete-header files (e.g. a browser `MediaRecorder` WebM) with
> `400 "Audio file might be corrupted or unsupported"`. Encode WAV client-side rather than
> uploading raw `MediaRecorder` WebM.

> **Reading the spoken transcript.** Audio-direct never produces a text transcript (the
> model understands the audio itself). To store/inspect the user's words, use a `transcribe`
> node (`saveAsUserMessage` → chat history), or read `GET /api/executions/{id}` → the
> transcribe (or START) step's `inputData`/output.

> **Parallel branches + voice.** A fork (a node with 2+ outgoing edges) runs its branches
> **concurrently**, sharing one DB session — so **two branches that both write to the DB at
> once currently error** (`session is provisioning a new connection`). For a voice fan-out
> (audio agent that saves history ∥ a transcribe/analysis branch), keep DB writes to ONE
> branch: set the analysis branch's `saveAsUserMessage: false` / agent `saveToHistory: false`
> and stash flags in `state` via SET_VARIABLE (state persists at finalization, no mid-run
> DB write). Both branches still emit their own `step_complete` SSE events.

**Voice output** — give an AGENT node `outputType: "voice"`. Non-streaming: the reply
audio is on `output.audio` (`{ base64, format, voiceId, model }`) — decode `base64` (mp3)
to play. Real-time: set the agent's `voice.realtime = true` and run with `stream: true`;
read **`audio_delta`** SSE events — the base64 PCM is in **`data.audio`** (with
`data.format` `pcm_16000` and optional `data.alignment` for lip-sync), not `data.base64`.

**Avatars** — `outputType: "avatar"` reuses the agent's streamed output to drive a
talking avatar; run with `stream: true` and subscribe to the SSE stream.

## Quick decision guide

- Simple request/response → §2 (sync).
- Might be slow / want to not hold a connection → §3 (`task:true` + poll `/api/workflows/task/{id}`).
- Live typing effect / long answers → §4 (`stream:true` + SSE `/api/executions/{id}/stream`).
- Multi-turn conversation → §5 (`createSession` then reuse `sessionId`).
- Speech in/out → §6.
