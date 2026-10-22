# Neural Bridge — Hardware Roadmap

Goal: replace the mock EEG loop with **real biological data from an OpenBCI Cyton**, drive the
existing intent engine and 3D hologram, and add a Gemini-backed response loop — while keeping the
deployed stack at **$0**.

Status: **v0.3** — the local bridge, three source modes, and the backend
contract are implemented and verified against BrainFlow's synthetic board
(32 unit tests + `scripts/verify_pipeline.py`). Real Cyton validation, Gemini,
voice, and CI are pending. The deployed backend still runs the mock generator
(`mode: mock`).

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
        │
        └── triggered frame ──▶ Gemini (server-side key) ──▶ orchestration message
```

### Why not `ws://localhost:8080` from the Vercel page?

- The deployed page is HTTPS; browsers block insecure `ws://` (mixed content).
- `localhost` in the browser is the *viewer's* machine, not the machine running BrainFlow.
- `NEXT_PUBLIC_WS_URL` is inlined at build time, so one bundle cannot point at each user's laptop.

The device socket above already exists and rebroadcasts to the topic the frontend subscribes to.

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

### Phase 4 — LLM bridge (Gemini) — next

- Key stays server-side (`GEMINI_API_KEY`); never `NEXT_PUBLIC_*`.
- New `POST /intent/respond` (or an ingest hook): fires only on `triggered`, with mode context.
- Hard timeout (~8 s) + deterministic-parser fallback.
- Rate limit (e.g. 1 request / 3 s) and token cap; log latency and cost.
- Configurable Flash model via env; no hardcoded model name.

**Done when:** conversation/creative modes respond to a real sustained state, and fail gracefully.

### Phase 5 — Voice I/O — planned

- v1 (free, no new service): browser Web Speech API for STT + `speechSynthesis` for TTS.
- Audio → transcript → `/intent/respond` with the current frame context.
- Typed-input fallback for browsers without Web Speech.
- Later: server-side STT/TTS if quality matters more than $0.

**Done when:** you can speak, see the transcript, and hear a reply that references your cognitive state.

### Phase 6 — Hardening — 🚧 partial

- ✅ 32 bridge unit tests (pytest) and `scripts/verify_pipeline.py` for the
  backend contract + synthetic pipeline.
- ✅ Frontend `typecheck`, `lint`, and production `build` pass.
- ⬜ pytest + `httpx` for the backend API surface; Playwright for the flows we
  verified manually.
- ⬜ GitHub Actions: typecheck, lint, build, pytest, Playwright.
- ⬜ Auth on `POST /devices` (registration secret) and `/intent/respond`.
- ⬜ Keep-alive monitor on `/health`; structured logs; Sentry free tier optional.
- Persistence: in-memory is fine for demos; Neon/Supabase free Postgres if
  history is needed.

---

## 4. Frontend changes

- ✅ Option page (`/settings`) with Demo / Online / Hardware, persisted in
  `localStorage`; URL resolution in `lib/source.ts`.
- ✅ `TelemetrySocket.tsx`: browser-side demo interval; WS for online/hardware;
  reconnect/backoff; mixed-content guard; preset push with device-command fallback.
- ✅ Store: `source`, `triggered`, connection status; source badge and mode-specific copy.
- ✅ Demo simulator: faithful TS port of `backend/app/simulator.py`.
- ⬜ `Hologram.tsx`: react to discrete `action` events (mode switch, select).
- ⬜ Voice panel (Web Speech API + typed fallback).

## 5. Backend changes

- ✅ `NEURAL_BRIDGE_MODE=live` path (no mock generator).
- ✅ `TelemetryFrame.triggered: bool = False`.
- ✅ Malformed device frames are ignored instead of closing the socket.
- ✅ A device's own frames are filtered out of its device-socket echo.
- ⬜ `app/llm.py` + `POST /intent/respond` (Gemini, timeout, fallback, rate limit).
- ⬜ Registration secret + auth/rate limiting on device and LLM endpoints.
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
| LLM cost/latency | trigger-only, rate limit, timeout, fallback |

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
