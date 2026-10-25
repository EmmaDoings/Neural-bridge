# Neural Bridge — Hardware Roadmap

Goal: replace the mock EEG loop with **real biological data from an OpenBCI Cyton**, drive the
existing intent engine and 3D hologram, and add a Gemini-backed response loop — while keeping the
deployed stack at **$0**.

Status: **v0.6.0** — the local EEG bridge, three source modes, Gemini response
loop, and the haptics output pipeline are implemented. Verified against
BrainFlow's synthetic board and a mock actuator (50 bridge/haptics unit tests +
14 backend tests + `scripts/verify_pipeline.py`). Device enrollment can be
protected with a registration secret; device commands and deletion require the
device API key. Real Cyton validation and physical motor/LRA validation remain
pending hardware. The deployed backend still runs the mock generator
(`mode: mock`); the deployed frontend includes `/settings`, the source selector,
the voice panel, and `/intent/respond`. Redeploy after this haptics change to
expose `/haptics/pulse` and the dashboard panel.

---

## 1. Architecture

The hardware bridge is a **client of the backend**, not a separate server for the browser.

```
OpenBCI Cyton (250 Hz, 8 ch)
        │  RFduino dongle (COM port)
        ▼
hardware/nb_bridge/  (local Python + BrainFlow)
        │  WS /ws/devices/{id}?api_key=…     ← existing endpoint
        ▼
Render backend  ──publish("*")──▶  WS /ws/telemetry  ──▶  Vercel frontend
        │                                                    │
        │                                                    │ POST /haptics/pulse
        │                                                    ▼
        └── command queue ──▶ hardware/nb_haptics ──▶ mock / serial actuator
        │
        └── triggered frame ──▶ Gemini (server-side key) ──▶ orchestration message
```

### Why not `ws://localhost:8080` from the Vercel page?

- The deployed page is HTTPS; browsers block insecure `ws://` (mixed content).
- `localhost` in the browser is the *viewer's* machine, not the machine running BrainFlow.
- `NEXT_PUBLIC_WS_URL` is inlined at build time, so one bundle cannot point at each user's laptop.

The device socket above already exists and rebroadcasts to the topic the frontend subscribes to. Hardware mode subscribes with `?kind=eeg`, so it excludes mock frames even when a local backend also runs the simulator.

---

## 2. Hardware

| Item | Detail |
| --- | --- |
| Board | OpenBCI Cyton (8 ch) or Cyton + Daisy (16 ch) |
| BrainFlow IDs | `CYTON_BOARD` (0) / `CYTON_DAISY_BOARD` (2) — verify against the installed BrainFlow version |
| Sample rate | 250 Hz (Cyton), 125 Hz (Daisy at 16 ch) |
| Connection | RFduino dongle → serial `COMx`; FTDI driver on Windows |
| Before coding | Confirm streaming + impedances in the OpenBCI GUI (< 10 kΩ, gel on dry-ish sites) |

### Suggested montage (Cyton, 8 ch)

| Ch | Site | Used for |
| --- | --- | --- |
| 1–2 | Fp1 / Fp2 | blink detection, frontal artifacts |
| 3–4 | C3 / C4 | attention / motor engagement |
| 5–6 | T7 / T8 | jaw-clench EMG |
| 7–8 | O1 / O2 | occipital alpha (eyes-closed) |

Reference: mastoid / linked ears; ground on the bias pin. Verify with the GUI before trusting numbers.

---

## 3. Phases

### Phase 0 — Foundation (no hardware needed) — ✅ implemented

- `hardware/nb_bridge/` using BrainFlow `SYNTHETIC_BOARD`.
- Register via `POST /devices`, stream over `WS /ws/devices/{id}`.
- Reconnect + **re-register on `4401` / HTTP 403** (the bus is in-memory and
  resets on Render restarts). `InvalidStatus` is handled because auth fails
  before the socket is accepted.
- `NEURAL_BRIDGE_MODE=live` disables the mock generator.

**Verified locally:** the synthetic bridge streams into a local live-mode
backend, 39–41 frames in 10 s, monotonic timestamps, all values in `[0, 1]`.
**Still pending:** pointing a real deployment's frontend at live-mode frames
(the deployed backend currently reports `mode: mock`).

### Phase 1 — Real telemetry — ✅ implemented (synthetic verified)

- Board reads run in a worker thread (`asyncio.to_thread`) so the WebSocket
  event loop stays responsive; `get_current_board_data(window)` every ~200 ms
  (5 Hz).
- Relative band powers via `DataFilter.get_custom_band_powers` (BrainFlow's
  2–45 Hz bands), with a 250-sample minimum and a flat-signal/NaN guard.
- Supports `synthetic`, `cyton` (8 ch @ 250 Hz) and `cyton_daisy` (16 ch @ 125 Hz).
- EMG uses `perform_bandpass(30–100 Hz)` on lateral channels; a `notch` helper
  is available for 50/60 Hz line noise.

**Verified:** the synthetic board produces valid frames. **Pending:** real Cyton
signal quality and impedance checks after the board arrives.

### Phase 2 — Metrics — ✅ implemented (synthetic verified)

- **Focus** = β_c / (β_c + θ_c), logistic-mapped to 0–1.
- **Meditation** = α_o / (α_o + β_o).
- **Attention** = β_c / (β_c + α_c + θ_c).
- Relative band power survives placement/session drift better than absolute power.
- 60 s calibration (eyes open, then closed) → per-user p5/p95 → map + clamp;
  falls back to the logistic curve if too few samples arrive.
- EMA smoothing (`NB_EMA_ALPHA=0.2`); flat/railed windows are rejected.

**Verified on synthetic data and unit tests. Pending:** real-user calibration
and a re-seat stress test.

### Phase 3 — Intent engine — ✅ implemented (synthetic verified)

- Sustained focus: `NB_INTENT_FOCUS_ENTER=0.85` for 1.5 s (≈ 8 frames at 5 Hz).
- Hysteresis (enter 0.85 / release 0.75) + 4 s cooldown; re-arms only after the
  metric drops below the release threshold.
- `confidence` is signal strength; `triggered` is a one-frame boolean so the UI
  reacts to the edge, not every frame.
- **EMG clench:** 30–100 Hz RMS on T7/T8/lateral, adaptive baseline, 2
  consecutive frames, 0.5 s cooldown → `motor_select` / `select`.
- Labels/colors mirror `backend/app/simulator.py` (`motor_select` is `#f97316`).

**Verified on synthetic data and unit tests. Pending:** real jaw-clench tuning
(false positives during speech). **Not implemented:** frontal blink detection.

### Phase 4 — LLM bridge (Gemini) — ✅ implemented

- `POST /intent/respond` receives a validated telemetry frame and optional
  transcript. It requires either a triggered frame or a transcript.
- Key stays server-side (`GEMINI_API_KEY`); never `NEXT_PUBLIC_*`.
- The configurable `GEMINI_MODEL` call has an ~8 s timeout, output cap, and
  deterministic fallback response. "Thinking" is disabled by default
  (`GEMINI_THINKING_BUDGET=0`) so a short output cap cannot truncate the answer;
  incomplete `MAX_TOKENS` responses are rejected and replaced by the fallback.
- The process-local rate limiter defaults to one request per 3 seconds **per
  client IP** (honouring `X-Forwarded-For` behind Render's proxy).

**Still pending:** production request authentication, a global daily quota, and
structured cost/latency telemetry.

### Phase 5 — Voice I/O — ✅ browser v1

- Browser Web Speech API captures speech where supported; `speechSynthesis`
  reads responses aloud.
- Voice and typed input call `/intent/respond` with the current frame context.
- Typed input remains available when browser speech recognition is unavailable.
- Later: server-side STT/TTS if quality matters more than $0.

**Still pending:** cross-browser manual testing with Chrome/Edge and a decision
on whether server-side STT/TTS is needed.

### Phase 6 — Hardening — 🚧 partial

- ✅ 50 bridge/haptics unit tests (pytest) and `scripts/verify_pipeline.py` for
  the backend contract, haptics pulse delivery, and synthetic pipeline.
- ✅ Frontend `typecheck`, `lint`, and production `build` pass.
- ✅ Backend pytest + `httpx` coverage for enrollment auth, API-key mutation
  protection, response fallback, validation, per-IP rate limiting, truncation
  handling, and timeout fallback.
- ✅ GitHub Actions workflow covers frontend typecheck/lint/build, backend tests,
  bridge tests, and the synthetic E2E pipeline; the same commands pass locally.
  The first hosted run is pending the next push.
- ⬜ Playwright coverage for browser flows.
- ✅ Optional registration secret on `POST /devices`; device commands and deletion require the per-device API key.
- ⬜ Authentication and a global daily quota for `/intent/respond` (per-IP rate limiting is implemented).
- ⬜ Keep-alive monitor on `/health`; structured logs; Sentry free tier optional.
- Persistence: in-memory is fine for demos; Neon/Supabase free Postgres if
  history is needed.

### Phase 7 — Haptics output — ✅ software path (physical pending)

- ✅ `hardware/nb_haptics/`: config, mock and serial drivers, pulse controller,
  CLI, and registration/reconnect through the shared `nb_common` client.
- ✅ `POST /haptics/pulse` with bounded intensity/duration, optional device
  targeting, per-client cooldown, and queue-saturation handling.
- ✅ Dashboard **Haptic output** panel: polls `GET /devices`, shows connection
  state, sends pulses, and never holds a device key.
- ✅ Serial line protocol (`PULSE <intensity> <ms>`) and reference
  Arduino/ESP32 firmware with MOSFET/driver wiring warnings.
- ✅ Unit tests (config, bounds, mock driver, controller, fake serial port) and
  E2E pulse delivery.
- ⬜ Physical ERM/LRA validation, PWM/frequency tuning, and enclosure/safety
  review. The `haptics`/`hologram` device kinds are still transport enums, not a
  claim that a physical hologram or touch surface exists.
- ⬜ Authenticated operator control for physical actuators; the endpoint is
  currently an unauthenticated demo path with CORS + per-IP cooldown.

---

## 4. Frontend changes

- ✅ Option page (`/settings`) with Demo / Online / Hardware, persisted in
  `localStorage`; URL resolution in `lib/source.ts`.
- ✅ `TelemetrySocket.tsx`: browser-side demo interval; WS for online/hardware;
  reconnect/backoff; mixed-content guard; hardware filtering to EEG sources.
- ℹ️ The browser no longer sends hardware commands because it must never hold a
  device API key. A future authenticated operator control path can expose
  selected commands safely.
- ✅ Store: `source`, `triggered`, connection status; source badge and mode-specific copy.
- ✅ Demo simulator: faithful TS port of `backend/app/simulator.py`.
- ⬜ `Hologram.tsx`: react to discrete `action` events (mode switch, select).
- ✅ Voice panel with browser speech recognition, speech synthesis, and typed fallback.
- ✅ Haptics panel: device status polling, intensity/duration controls, pulse
  delivery feedback, and mode-aware copy.

## 5. Backend changes

- ✅ `NEURAL_BRIDGE_MODE=live` path (no mock generator).
- ✅ `TelemetryFrame.triggered: bool = False`.
- ✅ Malformed device frames are ignored instead of closing the socket.
- ✅ A device's own frames are filtered out of its device-socket echo.
- ✅ Device command queue reports saturation as HTTP 429 instead of failing with
  an internal server error.
- ✅ Device removal and commands require the device API key; bridge enrollment
  optionally requires `DEVICE_REGISTRATION_KEY`.
- ✅ `app/llm.py` + `POST /intent/respond` (Gemini, timeout, fallback, per-IP rate limit, thinking disabled).
- ✅ `POST /haptics/pulse` (bounded pulse, optional target, per-IP cooldown,
  queue-saturation handling); the browser never receives the device key.
- ⬜ Broader API/WebSocket tests (source filtering, command saturation) and LLM/haptics authentication.
- ℹ️ Metrics/intent live in the local bridge (fast tuning, no backend hardware
  dependency); the backend stays a transport/broadcast layer.

---

## 6. Risks

| Risk | Mitigation |
| --- | --- |
| Render free cold starts | keep-alive pinger; frontend auto-reconnect already shipped |
| In-memory bus resets | bridge re-registers on `4401` |
| local → Render latency/jitter | measure; for click-critical demos run the stack locally |
| EEG signal quality | OpenBCI GUI impedance check first; relative band power; calibration |
| EMG false positives | hysteresis, cooldown, temporal-channel focus |
| Web Speech API support | Chrome/Edge only; keep a typed fallback |
| LLM cost/latency | per-IP rate limit, timeout, thinking disabled, fallback |
| Public `/intent/respond` abuse | per-IP rate limit + CORS; add a daily quota/auth before sharing widely |
| Public `/haptics/pulse` activates a physical actuator | per-IP cooldown + CORS; keep powerful actuators local, add operator auth before public use |
| Motor wiring / overdrive | bounded payloads in backend + bridge; MOSFET/driver, flyback diode, separate supply in the firmware guide |

## 7. Cost

Render free + Vercel Hobby + Gemini free/flash tier = **$0** hosting. The Cyton is a one-time
hardware cost.

## 8. Decisions and open questions

1. **Cyton 8-channel** is the target; `cyton_daisy` (16 ch) is supported by config
   if the board is upgraded.
2. **Metrics/intent run in the local bridge** — fastest tuning iteration and no
   hardware dependencies on Render. The backend validates and broadcasts.
3. **In-memory telemetry is enough** for the current demo; history is a later
   option (Neon/Supabase free Postgres).
4. **Gemini Flash, model name via env** (`GEMINI_MODEL`), server-side only.
5. **Haptics are queued by the backend**, not posted directly by the browser to a
   device socket. This keeps the device API key server-side and gives one place
   for bounds, cooldowns, and future operator auth.
