# Neural Bridge

Neural Bridge is a Brain-Computer Interface prototype that closes the gap
between reality, AI, and holograms. The goal is to make AI feel physically
present: something you can talk to face to face, influence with thought, see as
a hologram, and eventually touch through haptic or spatial interfaces.

**Current deployment**

- Frontend: <https://neural-bridge-umber.vercel.app>
- Backend: <https://neural-bridge-api.onrender.com> (`/health`)
- Cost: **$0** (Vercel Hobby + Render free tier + Gemini free tier)

The backend sleeps after ~15 minutes of inactivity, so the first load can take
~50 s. The frontend shows "Waking server…" and reconnects automatically.

## Three signal sources

The **Settings** page (`/settings`) lets you pick where frames come from. The
choice is stored in `localStorage` (`neural-bridge:source`) and survives reloads.

| Mode | Where the signal comes from | Needs a backend? | Needs hardware? |
| --- | --- | --- | --- |
| **Demo** (default) | A browser-side port of the backend simulator | No | No |
| **Online** | The configured/deployed backend (`NEXT_PUBLIC_API_URL`) | Yes | Optional |
| **Hardware** | A backend on this machine fed by the local bridge (`NEXT_PUBLIC_LOCAL_*`) | Local only | Yes (or synthetic board) |

Demo is the safe default: it works offline, produces frames at ~5.5 Hz, and
never mutates shared backend state. Online uses the deployed WebSocket. Hardware
is for a locally served frontend and warns when the page is HTTPS (browsers
block `ws://localhost` as mixed content).

## Stack

- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 3,
  Zustand 5, Three.js, Web Speech API (speech capture + synthesis)
- **Backend:** FastAPI, async WebSockets, Pydantic 2, in-memory device bus
- **Hardware:** Python 3, BrainFlow 5.23.0 (`SYNTHETIC_BOARD` or OpenBCI Cyton),
  `websockets` 17, `pyserial` 3.5
- **Haptics:** local `nb_haptics` bridge (mock or serial actuator) plus an
  Arduino/ESP32 reference firmware sketch
- **AI:** Gemini (`/intent/respond`, server-side key, deterministic fallback)
- **Deploy:** Render Blueprint + Vercel

## Project layout

```text
frontend/                 Next.js dashboard, 3D hologram, option page
backend/                  FastAPI telemetry, intent, device bus
hardware/                 BrainFlow + haptics bridges, firmware, tests
  nb_bridge/              EEG config, board session, signal, metrics, intent
  nb_haptics/             haptics config, drivers, controller, CLI
  nb_common/              shared device registration/WebSocket client
  haptics_firmware/       Arduino/ESP32 pulse firmware
  tests/                  bridge + haptics unit tests
scripts/                  dev helpers + scripts/verify_pipeline.py (E2E)
ROADMAP.md                Phases, risks, and what is verified vs pending
DEPLOY.md                 $0 deployment runbook
```

## Quick start

### Frontend only (Demo mode, no backend)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. Demo mode is selected by default, so the hologram
animates without a backend.

### Full local stack

Terminal 1 — backend:

```powershell
# from the repository root
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Terminal 2 — frontend:

```powershell
cd frontend
npm install
npm run dev
```

Terminal 3 — bridge (synthetic board):

```powershell
cd hardware
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:NB_API_BASE="http://localhost:8000"
# Only when the backend sets DEVICE_REGISTRATION_KEY, use the same value:
# $env:NB_DEVICE_REGISTRATION_KEY="<same value>"
.\.venv\Scripts\python -m nb_bridge
```

In the dashboard, open **Settings → Hardware → Save**. The bridge registers as a
device and its frames appear on `/ws/telemetry`.

Terminal 4 — haptics bridge (mock actuator):

```powershell
cd hardware
$env:NB_HAPTICS_API_BASE="http://localhost:8000"
.\.venv\Scripts\python -m nb_haptics
```

The **Haptic output** panel on the dashboard should show `haptic-hologram
connected`; **Send pulse** queues a bounded pulse to the bridge. For a real
motor, see the serial setup and wiring warnings in
[`hardware/README.md`](./hardware/README.md).

See [`hardware/README.md`](./hardware/README.md) for the Cyton setup, channel
mapping, calibration, haptics firmware, and troubleshooting.

## OpenBCI Cyton

The bridge is written and tested against BrainFlow's **synthetic board**. The
Cyton signal path (board id, serial port, 10–20 channel map) is implemented but
**has not been validated on real EEG yet** — the hardware has not arrived. Do not
treat the metrics as medical measurements.

When the board arrives:

```powershell
cd hardware
$env:NB_BOARD="cyton"
$env:NB_SERIAL_PORT="COM3"   # check Device Manager
$env:NB_CALIBRATION_SECONDS="60"
.\.venv\Scripts\python -m nb_bridge
```

Before trusting the output, verify streaming and impedances in the OpenBCI GUI
(< 10 kΩ), fix the reference, and re-seat the electrodes. The bridge rejects flat
and railed windows so a disconnected electrode cannot produce a confident intent.

## Haptics output

The dashboard's **Haptic output** panel calls `POST /haptics/pulse` with an
intensity (`0..1`) and duration (`10..2000 ms`). The backend selects a connected
device whose kind is `haptics` and queues a `pulse` command. The local bridge
validates the payload and drives either the mock actuator or a serial
Arduino/ESP32 controller. The browser never receives a device API key.

```powershell
cd hardware
.\.venv\Scripts\python -m nb_haptics --check --pulse   # mock, one test pulse
.\.venv\Scripts\python -m nb_haptics                   # wait for dashboard pulses
```

For a real ERM motor:

```powershell
$env:NB_HAPTICS_DRIVER="serial"
$env:NB_HAPTICS_SERIAL_PORT="COM4"
.\.venv\Scripts\python -m nb_haptics
```

Upload [`haptics_firmware/haptics_firmware.ino`](./hardware/haptics_firmware/haptics_firmware.ino)
and close the Arduino Serial Monitor. **Never connect a motor directly to a GPIO
pin**; use a MOSFET/driver, flyback diode, and a separate motor supply. The mock
path and serial protocol are tested; a physical motor and LRA output are still
pending hardware validation. The pulse endpoint has a per-IP cooldown but no
user login, so keep powerful actuators off the public deployment.

## Tests and verification

```powershell
# Bridge + haptics unit tests (50)
cd hardware
.\.venv\Scripts\python -m pytest tests -q

# Frontend
cd ..\frontend
npm run typecheck
npm run lint
npm run build

# Full contract + synthetic pipeline (starts a throw-away backend)
cd ..\hardware
.\.venv\Scripts\python ..\scripts\verify_pipeline.py
```

The E2E script verifies device registration, `triggered` propagation, malformed
frame tolerance, command delivery, no self-echo, haptics pulse delivery, and ≥20
valid frames in 10 s.

## Current prototype scope

- Three selectable signal sources (Demo / Online / Hardware) with a persisted
  option page
- Mock simulator with seven cognitive presets, shared by the backend and the
  browser-side Demo mode
- WebSocket telemetry with reconnect/backoff and cold-start messaging
- Local BrainFlow bridge: synthetic and Cyton/Daisy, calibration, EMA smoothing,
  relative band powers, artifact gate, EMG clench detection, intent hysteresis
- Device bus: registration, API-key auth, command delivery, own-frame filtering
- Reactive 3D hologram (drag to rotate, scroll to zoom, tap to switch modes)
- Gemini-backed `/intent/respond` endpoint with a timeout, rate limit, and
  deterministic fallback when no key is configured
- Browser voice capture and speech synthesis, plus a typed-input fallback
- Haptics output pipeline: browser-safe pulse endpoint, mock/serial bridge,
  Arduino reference firmware, and a dashboard pulse/status panel

## Deploy for $0

Backend on Render, frontend on Vercel:

- Step-by-step guide: [`DEPLOY.md`](./DEPLOY.md)
- Render Blueprint: [`render.yaml`](./render.yaml)
- Phase plan and status: [`ROADMAP.md`](./ROADMAP.md)

### Gemini and voice setup

Set `GEMINI_API_KEY` on the backend only. The dashboard sends telemetry and an
optional voice transcript to `POST /intent/respond`; the key is never sent to
the browser. `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS`,
`GEMINI_MAX_OUTPUT_TOKENS`, and `INTENT_RATE_LIMIT_SECONDS` tune the service.
When the key is absent or Gemini is unavailable, the endpoint returns a
deterministic response from the current telemetry so the interface remains
usable.

Voice input uses the browser's Web Speech API where available and always shows
a text field as a fallback. Speech synthesis reads successful replies aloud.

## Safety

Experimental prototype, not a medical device. EEG-derived metrics are noisy and
user-specific. Never use Neural Bridge for diagnosis, treatment, or any
safety-critical decision.
