# Integrating an Assemblix voice agent

How to put a **voice agent** into your own product: mint a call token on your
backend, open the WebSocket from your frontend, stream audio both ways, attach
workflows that analyse the conversation, and read calls back afterwards.

> Source of truth: this mirrors the public docs pages `docs/voice-agents/*`.
> `BASE` is your instance base URL (the same `ASSEMBLIX_API_URL` the MCP uses,
> e.g. `https://app.assmblx.com`). Auth is the same project `sk_` key.

## 0. What a voice agent is — and is not

A voice agent is **not a workflow**. It has no graph. The caller's audio goes
straight to a speech-to-speech model and the answer comes straight back, because
anything on that path is heard as a pause. What you configure is a prompt, a
voice, knowledge inlined into the prompt, and optional workflows that watch.

Do not confuse it with **voice inside a workflow** (the `transcribe` node, an
agent node with voice output). That is one blob of audio in, one run, one answer.
Both features exist; they share nothing.

Author agents with the `create_voice_agent` / `update_voice_agent` tools, not by
hand — the `config` object is nested and easy to get wrong.

## 1. Mint a call token (your backend)

```
POST {BASE}/api/voice-agents/{voiceAgentId}/sessions
Authorization: Bearer sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Content-Type: application/json

{ "clientId": "your-end-user-id" }
```

```json
{ "token": "eyJhbGciOi…", "expiresIn": 60 }
```

The body is optional and has exactly one field, `clientId`. Nothing else is read —
an unknown field is silently dropped, so a typo here fails quietly.

Rules that matter:

- **The `sk_` key never goes to the browser.** This call belongs on your server,
  behind your own auth. The token that comes back authorizes exactly one call
  with one agent.
- **Mint on the button press, not on page load.** It expires in 60 seconds, and
  that short life is the entire security model.
- An inactive agent returns `400`.

### Tying a call to one of your users

`clientId` is the same identifier `POST /api/executions` takes, and it means the
same thing here: everything done under it shares one **client session**, and
therefore one copy of project state.

Pass it and it is sealed into the token, so it survives into the WebSocket — which
carries no body of its own. From there it lands on the call and on **every
analysis workflow the call starts**, per-turn and final alike. Those workflows
then read and write the same project state your other workflows use for that user,
which is what makes scoring that accumulates across calls and chats possible.

Omit it and the call is anonymous: the hooks still run, but with no client session,
so whatever they write to project state has nowhere to persist. Any scoring that
is supposed to add up over time silently adds up to nothing.

Read and write those variables with `list_project_state_variables` and the rest of
the project-state tools; a workflow reaches them as `project.<name>`.

## 2. Open the socket (your frontend)

```
wss://{BASE_HOST}/api/voice-agents/sessions/{token}/stream
```

No headers — a browser WebSocket handshake cannot carry `Authorization`, which is
why the token is in the path.

**You send:**

| Frame | Meaning |
| --- | --- |
| binary | PCM16 mono little-endian at `inputSampleRate` |
| `{"type":"session.stop"}` | Hang up |

**You receive:**

| Frame | Meaning |
| --- | --- |
| `{"type":"session.ready","inputSampleRate":N,"outputSampleRate":N}` | Connected. Send no audio before this. |
| binary | Agent speech, PCM16 mono at `outputSampleRate` |
| `{"type":"transcript","role":"user"\|"assistant","text":"…","isFinal":bool}` | Captions; non-final frames replace the previous one |
| `{"type":"speech.started"}` | Caller cut in — drop queued playback |
| `{"type":"turn.timings","firstAudioMs":N}` | Last inbound audio → first audio back |
| `{"type":"error","code":…,"message":…,"isFatal":bool}` | Non-fatal errors are normal; log and continue |
| `{"type":"session.closed","reason":"…"}` | Terminal: `user_hangup`, `timeout`, `error`, `completed`, `provider_closed` |

## 3. The three things people get wrong

**Sample rates are not a constant.** OpenAI Realtime is 24 kHz both ways; Gemini
Live listens at 16 kHz and answers at 24 kHz. They arrive in `session.ready` and
change if the agent's provider changes. Build the capture graph at
`inputSampleRate` and play back at `outputSampleRate` — `new AudioContext({
sampleRate })` converts natively. Never resample by hand.

**Capture must start after `session.ready`,** not while the socket is opening —
you do not know the rate until then.

**Barge-in needs every queued source stopped.** An `AudioBufferSourceNode` plays
to its end once started, so moving your schedule pointer on `speech.started` is
not enough: call `stop()` on each source still queued. Skip this and the agent
talks over the caller for as long as your buffer is deep. It is the single
difference between a call that feels alive and one that feels like an IVR.

Two smaller ones: capture in an `AudioWorklet` (~200 ms frames), not on the main
thread; and route the worklet through a **muted** gain node into the destination —
a worklet only runs while connected to the graph, but the microphone must never
reach the speakers.

## 4. Attaching workflows (the part only Assemblix has)

A voice agent can start ordinary workflows while it talks. Set
`turn_workflow_id` and `final_workflow_id` on the agent.

Both are **fire-and-forget in this version**: the conversation never waits for
them, and their output does not flow back into what the agent says. A workflow
that fails is logged and dropped; it cannot end a call.

**Per-turn** — once per finished caller utterance:

```json
{
  "message": "I'd like to book an appointment for Tuesday",
  "client_id": "your-end-user-id",
  "voice": {
    "session_id": "…",
    "turn_index": 3,
    "agent_reply": "Of course — what day suits you?"
  }
}
```

**Final** — once, after the call:

```json
{
  "message": "user: hello\nassistant: hi, how can I help?\n…",
  "client_id": "your-end-user-id",
  "voice": {
    "session_id": "…",
    "transcript": [{ "role": "user", "text": "hello" }],
    "duration_sec": 74.2,
    "end_reason": "user_hangup"
  }
}
```

`client_id` is present only if the call was minted with one. It is not readable as
input — it is what binds the run to a client session, so the workflow reads and
writes `project.<name>` for that user instead.

Reach the rest from a node as `input.message`, `input.voice.turn_index`, and so on.
Author these workflows with the workflow tools and `publish_workflow` them —
runs always execute the published snapshot.

Typical uses: extract structured data per turn; on the final hook, write to a
CRM, score the call, or alert a human.

## 5. Reading calls back

```
GET {BASE}/api/voice-agents/{voiceAgentId}/sessions?page=1&limit=50
GET {BASE}/api/voice-sessions/{voiceSessionId}
```

Or, from here, the `list_voice_calls` and `get_voice_call` tools. The detail
carries the transcript, duration, cost, token counts, and every analysis run with
an `executionId` you can open with `get_execution_detail`.

Every call carries the `clientId` it was minted with (`null` when it was minted
without one), so you can group an agent's calls by end-user from the list alone.

Calls placed with a project API key are real; calls placed from the editor carry
`isDebug: true` — the editor's test call is always anonymous.

**Read transcripts before editing a prompt.** What an agent gets wrong on a real
call is rarely what you would predict from reading its instructions.

## 6. Cost

A call is billed by wall-clock time at the model's per-minute price, which
`list_conversation_voices` reports next to each model. Long knowledge bases cost
money on every call and slow the first reply, because they are inlined into the
prompt at session start rather than retrieved mid-call.

## 7. Choosing a provider

**OpenAI Realtime** — best interruption handling; non-English audio is audibly
accented. Supports custom voices: an id created through OpenAI's
`/v1/audio/voices` works anywhere a built-in voice name does.

**Gemini Live** — markedly better non-English speech across 70+ languages;
weaker barge-in. Prebuilt voices only.
