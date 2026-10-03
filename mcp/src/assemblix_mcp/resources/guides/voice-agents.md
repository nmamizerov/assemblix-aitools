# Integrating an Assemblix voice agent

How to put a **voice agent** into your own product: mint a call token on your
backend, open the WebSocket from your frontend, stream audio both ways, attach
workflows that analyse the conversation, and read calls back afterwards. An agent
can also have a lip-synced **avatar**; that call shape is covered in §8. An agent
runs either on one speech-to-speech model (**realtime**, the default) or as a
**cascade** of streaming STT → a text LLM → streaming TTS; the cascade is covered
in §9. The call protocol is the same for both.

> Source of truth: this mirrors the public docs pages `docs/voice-agents/*`.
> `BASE` is your instance base URL (the same `ASSEMBLIX_API_URL` the MCP uses,
> e.g. `https://app.assmblx.com`). Auth is the same project `sk_` key.

## 0. What a voice agent is — and is not

A voice agent is **not a workflow**. It has no graph. The caller's audio goes
straight to a speech-to-speech model (or, in cascade mode, through a streaming
recognizer, a text model and a streaming synthesizer) and the answer comes straight
back, because anything on that path is heard as a pause. What you configure is a
prompt, a voice, knowledge inlined into the prompt, and optional workflows that
watch.

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
{ "token": "eyJhbGciOi…", "expiresIn": 60, "media": null }
```

`media` is `null` for a voice-only agent. For an agent with an avatar it carries a
LiveKit room to join — see §8. Forward it to your frontend together with `token`.

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
| `{"type":"session.ready","inputSampleRate":N,"outputSampleRate":N,"media":"ws"}` | Connected. Send no audio before this. `media` is `"livekit"` on an avatar call (§8). |
| binary | Agent speech, PCM16 mono at `outputSampleRate` |
| `{"type":"transcript","role":"user"\|"assistant","text":"…","isFinal":bool}` | Captions; non-final frames replace the previous one |
| `{"type":"speech.started"}` | Caller cut in — drop queued playback |
| `{"type":"turn.timings","firstAudioMs":N}` | Last inbound audio → first audio back; cascade calls add per-stage fields (§9) |
| `{"type":"error","code":…,"message":…,"isFatal":bool}` | Non-fatal errors are normal; log and continue |
| `{"type":"session.closed","reason":"…"}` | Terminal: `user_hangup`, `timeout`, `error`, `completed`, `provider_closed`; on avatar calls also `avatar_busy`, `avatar_unavailable` (§8) |

## 3. The three things people get wrong

**Sample rates are not a constant.** OpenAI Realtime is 24 kHz both ways; Gemini
Live listens at 16 kHz and answers at 24 kHz; a cascade listens at 16 kHz and
answers at its TTS provider's rate. They arrive in `session.ready` and
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

A realtime call is billed by wall-clock time at the model's per-minute price,
which `list_conversation_voices` reports next to each model. A cascade call is
billed per stage — recognized minutes, LLM tokens, synthesized characters — see §9. Long knowledge bases cost
money on every call and slow the first reply, because they are inlined into the
prompt at session start rather than retrieved mid-call.

## 7. Choosing a provider

**OpenAI Realtime** — best interruption handling; non-English audio is audibly
accented. Supports custom voices: an id created through OpenAI's
`/v1/audio/voices` works anywhere a built-in voice name does.

**Gemini Live** — markedly better non-English speech across 70+ languages;
weaker barge-in. Prebuilt voices only.

**Cascade** (`mode="cascade"`, §9) — not a provider but a different engine:
Yandex SpeechKit recognition, any OpenAI/Gemini/DeepSeek text model, a streaming
TTS. An order of magnitude cheaper per hour, native Russian voices, audio stays
with providers you choose, no provider session cap. The price is a few hundred
milliseconds more per turn and a server that needs setup (§9). Pick it for
Russian-language calls, long calls, high volume, or when the realtime providers
are not an option for your data.

## 8. Avatar calls (a face that speaks)

An agent can carry a lip-synced avatar. The caller sees a face and hears the
agent's own voice (native realtime or an external TTS) coming out of it.

### How it is wired — and why

**Your client talks only to Assemblix, never to the avatar vendor.** Video cannot
ride the voice WebSocket cheaply, so an avatar call adds a second connection:

- the **WebSocket** stays exactly as in §2, but carries only control frames
  (`session.ready`, transcripts, `speech.started`, `turn.timings`, `error`,
  `session.closed`) — no binary audio in either direction;
- the **media** (the caller's microphone up, the avatar's audio + video down) goes
  through a **LiveKit** room hosted by the Assemblix deployment. The Assemblix
  server joins it as `agent`, the avatar vendor joins it as `avatar`, your
  browser joins it as `user`.

Changing the avatar vendor is a server-side change; your client code does not move.

### Prerequisites (one-time, not your code)

1. The Assemblix server has LiveKit configured (`LIVEKIT_URL`,
   `LIVEKIT_PUBLIC_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`). Without it the
   API rejects an avatar on the agent with `400 Avatars need LiveKit`.
2. An avatar-provider credential (an **Anam** API key) is added in the Assemblix
   UI under Credentials. Avatars are bring-your-own-key: the vendor bills that key.
3. The agent has an avatar: `list_avatars(credential_id)` → pick an avatar and a
   model → `update_voice_agent(voice_agent_id, avatar_credential_id=…,
   avatar_id=…, avatar_model=…)` (or pass the same on `create_voice_agent`).
   `remove_avatar=True` turns it back into a voice-only agent.

### Your backend

Identical to §1 — same endpoint, same `sk_` key, same 60-second token. The only
difference is the response:

```json
{
  "token": "eyJhbGciOi…",
  "expiresIn": 60,
  "media": {
    "transport": "livekit",
    "url": "wss://rtc.example.com",
    "token": "eyJhbGciOi…"
  }
}
```

Return the whole object to your frontend. `media.token` lets its holder join that
one room and publish a microphone — nothing else — so it is as safe to hand to the
browser as `token`. It is also short-lived: join right away.

```ts
// Node / Express — your server
app.post("/api/call", requireUser, async (req, res) => {
  const r = await fetch(`${BASE}/api/voice-agents/${AGENT_ID}/sessions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.ASSEMBLIX_SK}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ clientId: req.user.id }),
  });
  if (!r.ok) return res.status(r.status).send(await r.text());
  res.json(await r.json()); // { token, expiresIn, media }
});
```

### Your frontend

`npm i livekit-client`. Order matters: **join the room and publish the mic first,
then open the WebSocket.** The server waits (up to ~20 s) for your microphone and
the avatar's video before it sends `session.ready`.

```ts
import { Room, RoomEvent, Track } from "livekit-client";

export async function startAvatarCall(video: HTMLVideoElement) {
  // Ask for the mic inside the click handler, before anything is minted.
  const mic = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  const { token, media } = await fetch("/api/call", { method: "POST" }).then((r) => r.json());

  let socket: WebSocket | null = null;
  let avatarAudio: HTMLMediaElement | null = null;
  const room = new Room({ adaptiveStream: true, dynacast: true });

  const hangUp = () => {
    room.removeAllListeners();
    void room.disconnect();
    avatarAudio?.remove();
    mic.getTracks().forEach((t) => t.stop());
    socket?.close();
  };

  room.on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
    if (participant.identity !== "avatar") return;
    if (track.kind === Track.Kind.Video) {
      track.attach(video); // <video autoplay playsinline muted>
    } else if (track.kind === Track.Kind.Audio) {
      avatarAudio = track.attach(); // not muted: this is the agent's voice
      avatarAudio.hidden = true;
      document.body.appendChild(avatarAudio);
    }
  });
  // The server deletes the room *before* it sends session.closed with a reason.
  // Only treat a room disconnect as the end once the control socket is gone.
  room.on(RoomEvent.Disconnected, () => {
    if (!socket || socket.readyState !== WebSocket.OPEN) hangUp();
  });

  await room.connect(media.url, media.token);
  await room.localParticipant.publishTrack(mic.getAudioTracks()[0]);

  socket = new WebSocket(`wss://${BASE_HOST}/api/voice-agents/sessions/${token}/stream`);
  socket.onmessage = (event) => {
    if (typeof event.data !== "string") return; // no binary audio on avatar calls
    const frame = JSON.parse(event.data);
    switch (frame.type) {
      case "session.ready":
        // frame.media === "livekit": nothing to capture or play here — LiveKit does it.
        showLive();
        break;
      case "transcript":
        renderCaption(frame.role, frame.text, frame.isFinal);
        break;
      case "session.closed":
        if (frame.reason === "avatar_busy") showError("The avatar is busy — try again in a minute.");
        if (frame.reason === "avatar_unavailable") showError("The avatar could not start.");
        hangUp();
        break;
    }
  };
  socket.onclose = hangUp;

  return () => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "session.stop" }));
    hangUp();
  };
}
```

`showLive`, `renderCaption` and `showError` are yours. Barge-in needs no code on
your side: when the caller talks over the avatar, the server stops it.

### What goes wrong

- **Capturing or playing audio over the WebSocket on an avatar call.** Nothing
  arrives there and nothing you send is heard; the mic must be the LiveKit track.
  Branch on `media` (mint response) or `session.ready.media`.
- **Ending the call on the room's `Disconnected` while the socket is open.** On a
  failure the server deletes the room first and sends the reason second; tearing
  down on the room event loses the reason and the call just "stops".
- **A muted or detached audio element.** The avatar's voice is its own audio track;
  mute only the `<video>`. Safari can still block autoplay after long async gaps —
  listen for `RoomEvent.AudioPlaybackStatusChanged` and call `room.startAudio()`
  from a user gesture if `room.canPlaybackAudio` is false.
- **A client watchdog shorter than the server's.** Setup takes a few seconds (the
  avatar joins while the model connects); allow ~30 s before giving up.
- **Redialing instantly after `avatar_busy`.** The vendor counts sessions per key
  and releases them with a delay; a free plan may allow just one at a time.

### Close reasons specific to avatars

| Reason | Meaning | What to tell the user |
| --- | --- | --- |
| `avatar_busy` | The vendor refused a new session: its concurrency limit for that key is reached | Try again in a minute |
| `avatar_unavailable` | Anything else: vendor error, LiveKit unreachable, the avatar or your mic did not join in time, the agent lost its avatar after the token was minted | The avatar could not start |

### Limits in this version

- Interrupting the avatar is most reliable with **OpenAI Realtime** voices. With
  **Gemini Live** the avatar can only be interrupted while the model is still
  generating its reply.
- Latency: the avatar adds its render time on top of the voice round trip (about
  a second in practice). It depends on the vendor and on where LiveKit runs
  relative to the vendor and to your users.
- Avatar minutes are billed by the vendor on your key, not by Assemblix.

## 9. Cascade mode (STT → brain → TTS)

A cascade agent does not hand the call to one speech-to-speech model. The
Assemblix server runs the turn itself: a voice-activity model and **Smart Turn**
decide when the caller has finished, **Yandex SpeechKit** streams the recognized
text, a **text LLM** (the brain) streams a reply, and a **streaming TTS** speaks it
sentence by sentence while the rest is still being written. Your client cannot
tell the difference: same token, same WebSocket, same frames (§1–§3), avatars work
the same way (§8).

### When to choose it

| | Realtime | Cascade |
| --- | --- | --- |
| Cost | per-minute model price | ~22–95 ₽ per hour of conversation, depending on the brain and how much the agent talks |
| Russian | accented (OpenAI) to good (Gemini) | native Yandex voices |
| Data | audio goes to OpenAI/Google | audio goes to Yandex; text to the LLM you pick |
| Call length | capped by the provider's session limit | only your server's `VOICE_SESSION_MAX_SECONDS` |
| Latency | lowest | a few hundred ms more per turn, if configured as below |
| The model | fixed speech-to-speech model | any OpenAI / Gemini / DeepSeek text model |

### Server prerequisites (self-host)

A cascade call that cannot start ends with `session.closed` before
`session.ready`. Check these once per deployment:

1. **Turn-detection weights** (Silero VAD + Smart Turn v3, ONNX). The Docker image
   downloads them at build time into `/opt/turn-models` (`TURN_MODELS_DIR`).
   Running natively: `make turn-models` in `assemblix-app-api`. Missing → reason
   `setup_failed`.
2. **Yandex SpeechKit** for recognition and the default voice:
   `SYSTEM_YANDEX_SPEECHKIT_API_KEY` + `SYSTEM_YANDEX_SPEECHKIT_FOLDER_ID`, or a
   Yandex credential in the UI passed as `stt_credential_id` / `tts_credential_id`.
3. **The brain's LLM key**: `SYSTEM_GEMINI_API_KEY` (or the OpenAI / DeepSeek
   one), or a credential passed as `brain_credential_id`. `GEMINI_API_BASE_URL`
   routes Gemini through a proxy — and its distance is added to every turn.
4. **Call length**: `VOICE_SESSION_MAX_SECONDS` defaults to 600 (10 minutes), after
   which the call closes with `timeout`. Raise it (e.g. 3600) for long calls.

### Recommended config

`create_voice_agent(mode="cascade", …)` with nothing else gives this (the
essential part of the config it writes):

```json
{
  "mode": "cascade",
  "voice": null,
  "tts": { "provider": "yandex", "model": "yandex-tts-v3-chunk", "voiceId": "alena", "realtime": true },
  "cascade": {
    "stt": { "provider": "yandex", "model": "general" },
    "turn": {},
    "brain": {
      "type": "prompt",
      "provider": "gemini",
      "model": "gemini-3.1-flash-lite",
      "params": { "thinking_level": "minimal", "max_tokens": 300 }
    }
  }
}
```

Choose other parts with `list_cascade_options`:

- **TTS must be a streaming model** — only those `list_cascade_options` lists
  under `tts`. `yandex-tts-v3-chunk` is the cheapest: it speaks the first
  sentence at once and packs the rest into ~250-character requests.
  `yandex-tts-v3` synthesizes sentence by sentence for the most natural
  intonation; `yandex-tts-v3-stream` has the lowest time to first audio. ElevenLabs
  streaming models work too, at ElevenLabs prices. Yandex voices: `alena`,
  `filipp`, `ermil`, `jane`, `omazh`, `zahar`, `dasha`, …
- **The brain** is a plain chat model. Keep it small and fast; a large model's
  intelligence is heard as silence. `brain_params` are the provider's usual
  parameters: `thinking_level` (Gemini 3) and `max_tokens` matter most.
  `history_turns` (default 40) is how many messages stay in its context verbatim.

### Writing the prompt for a cascade

The brain is a text model that does not know it is being read aloud. Measured on
a live instance with default thinking and a chat-style prompt: 1.4–3.7 s to the
first token, and long markdown replies read out in full. Hence the defaults —
`thinking_level: "minimal"`, `max_tokens: 300` — and a prompt that tells it:

- it is on a phone call and everything it writes is spoken;
- 1–3 short sentences per reply, one question at a time;
- no markdown, lists, headings, emoji, links, or tables;
- numbers, dates and abbreviations as they should be pronounced.

Keep `max_tokens` around 300 as a backstop: a runaway reply is a monologue the
caller has to interrupt.

### Tuning end of turn

After `min_silence_ms` of silence (default 200) Smart Turn looks at the
utterance and says whether it sounds finished. If the probability reaches
`smart_turn_threshold` (default 0.5) the turn ends there; if not, the server
waits until `max_silence_ms` (default 1500) of silence. With `smart_turn=False`
every turn waits the full `max_silence_ms`.

- **The agent cuts callers off** → raise `min_silence_ms` (300–500) or
  `smart_turn_threshold` (0.6–0.7).
- **Long pauses before every reply** → check `eouMs` (below). Near
  `max_silence_ms` means Smart Turn keeps saying "not finished": lower
  `max_silence_ms` (1000–1200) or `smart_turn_threshold`.

Known limitation: on hesitant speech ("um… so… I'd like…") Smart Turn may judge
the utterance unfinished and the server waits the whole `max_silence_ms`. That
is the trade-off between cutting people off and waiting; tune for your callers.

### Reading the timings

Every cascade reply sends one `turn.timings` frame:

```json
{ "type": "turn.timings", "eouMs": 220, "sttFinalMs": 90, "brainFirstTokenMs": 480,
  "ttsFirstAudioMs": 310, "totalMs": 1100, "firstAudioMs": 1100 }
```

`get_voice_call` returns the same per reply (`timings` on each assistant line of
the transcript) and `timingSummary` — `{stage: {p50, p95}}` for the whole call.
Read p95 before p50: callers remember the worst pause.

| Stage | Measures | When it is slow |
| --- | --- | --- |
| `eouMs` | caller stops → server decides the turn is over | see "Tuning end of turn" |
| `sttFinalMs` | turn over → final recognized text (gives up after 0.3 s and uses the partial) | the SpeechKit endpoint is far away or overloaded; a proxy in `YANDEX_STT_V3_GRPC_ENDPOINT` adds its hop |
| `brainFirstTokenMs` | text sent to the LLM → first token back | thinking (set `thinking_level: "minimal"`), a long prompt or knowledge base, a large model, or a distant `GEMINI_API_BASE_URL` proxy |
| `ttsFirstAudioMs` | first token → first audio frame sent | try `yandex-tts-v3-stream`; a reply that opens with a long sentence waits for that sentence |
| `totalMs` / `firstAudioMs` | caller stops → first audio | the sum of the above |

In practice the brain is the stage that goes wrong. Fix it first.

### When a cascade call fails

| You see | Meaning | Fix |
| --- | --- | --- |
| `session.closed` `setup_failed` before `session.ready` | The server could not build the pipeline — most often the turn-detection weights are missing | Prerequisite 1; the server log says which |
| `session.closed` with a sentence as the reason, before `session.ready` | Configuration rejected: e.g. `Voice model … has no streaming route`, `System API key for … is not configured` | Pick a streaming TTS; set the key or pass a credential |
| `error` `stt_unavailable` / `stt_failed`, `isFatal: true`, then `session.closed` `error` | Recognition could not start or died mid-call | SpeechKit key, folder id, network to Yandex |
| `error` `tts_unavailable`, `isFatal: true`, then `session.closed` `error` | The synthesizer failed | TTS key, voice id, network to the provider |
| `error` `brain_timeout`, `isFatal: false` | No reply text within 5 s; that turn gets no answer, the call goes on | Thinking, prompt size, model, proxy — see `brainFirstTokenMs` |
| `error` `brain_failed`, `isFatal: false` | The LLM call failed (key, model id, a rejected param); the call goes on | Check `brain_model` and `brain_params` against `list_cascade_options` |

### Limits in this version

- Recognition is Yandex SpeechKit only; it is strongest in Russian.
- The brain is a prompt with knowledge inlined, like a realtime agent; it cannot
  call tools mid-call. Analysis workflows (§4) work as usual.
- Barge-in is detected by the server: when the caller speaks over the agent,
  `speech.started` arrives as usual, and the brain remembers only the part of its
  reply the caller actually heard.
