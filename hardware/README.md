# Neural Bridge hardware bridges

This directory contains two local Python processes that are *clients* of the
backend, never servers for the browser:

- **`nb_bridge`** turns an **OpenBCI Cyton** (or BrainFlow's synthetic board)
  into telemetry frames.
- **`nb_haptics`** receives bounded pulse commands and drives a mock or serial
  actuator (the output side of the hologram).

```
OpenBCI Cyton ──USB dongle──▶ nb_bridge (BrainFlow + metrics + intent)
                                      │
                                      │  POST /devices
                                      │  WS /ws/devices/{id}?api_key=…
                                      ▼
                              FastAPI backend
                                │           ▲
              publish("*")      │           │  POST /haptics/pulse
                                ▼           │  (browser-safe, no device key)
                         WS /ws/telemetry   │
                                │      nb_haptics (mock / serial actuator)
                                ▼           ▲
                         Next.js dashboard ─┘
```

The bridge registers itself, computes metrics and intent locally, and streams
one frame per `NB_UPDATE_HZ` over the existing device socket. Frames are
rebroadcast to every `/ws/telemetry` subscriber, which is what the dashboard
reads.

## What is verified

| Area | Status |
| --- | --- |
| BrainFlow 5.23.0 API (PSD, band powers, filters, EMG) | Verified empirically |
| Synthetic board end to end | Verified (≥20 frames in 10 s, valid ranges) |
| Backend contract (`triggered`, malformed frames, commands, no self-echo) | Verified |
| Haptics command path (mock actuator, registered device → backend → pulse) | Verified |
| Serial line protocol (fake serial port) | Verified by unit tests |
| Unit tests | 50 passing |
| Real Cyton signal quality / impedances / EMG thresholds | **Pending hardware arrival** |
| Real motor / LRA output, firmware on physical hardware | **Pending hardware arrival** |

The code path for the Cyton is the same as the synthetic path; only the board id,
serial port and channel names change. It has **not** been validated on real EEG
yet. Do not treat the metrics as medically meaningful.

## Install

Requires Python 3.11+ (3.13 is what Render uses; the bridge also runs on newer
versions). From this directory:

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

`requirements.txt` pins `brainflow==5.23.0`, `websockets==17.2`, and
`pyserial==3.5`. Hardware dependencies are **not** installed on Render; the
deployed backend stays lightweight. The haptics bridge in mock mode does not
need pyserial, but it is included so the serial actuator path works after the
same install.

## Quick check

Synthetic board, deployed backend:

```powershell
.\.venv\Scripts\python -m nb_bridge --check
```

This validates the config, calls `GET /health`, opens the board, and prints one
frame. Exit code `0` means everything worked. Add `--no-board` to check the
config and backend only.

## Run

### Synthetic (no hardware)

```powershell
.\.venv\Scripts\python -m nb_bridge
```

### OpenBCI Cyton

1. Plug in the RFduino dongle.
2. Find the serial port in Device Manager (Windows: `COM3`, `COM4`, …;
   macOS/Linux: `/dev/ttyUSB0`, `/dev/tty.usbserial-…`).
3. Close the OpenBCI GUI if it owns the port.
4. Run:

```powershell
$env:NB_BOARD="cyton"
$env:NB_SERIAL_PORT="COM3"
.\.venv\Scripts\python -m nb_bridge
```

### Validate a real Cyton before streaming

First check impedance and the signal in the OpenBCI GUI. Then, with the GUI
closed so it releases the serial port, collect a 30-second local validation
sample. The command checks that at least 80% of expected metric windows produce
valid telemetry; it does not transmit telemetry to the backend.

```powershell
$env:NB_BOARD="cyton"
$env:NB_SERIAL_PORT="COM3"
.\.venv\Scripts\python validate_cyton.py --seconds 30
```

Cyton + Daisy is supported with `NB_BOARD=cyton_daisy`; it streams 16 EEG
channels at 125 Hz. The default region map expects the standard 10–20 names
(`Fp1`, `Fp2`, `C3`, `C4`, `P7`, `P8`, `O1`, `O2` for a Cyton).

### Point at a local backend (Hardware source mode)

```powershell
$env:NB_API_BASE="http://localhost:8000"
.\.venv\Scripts\python -m nb_bridge
```

Start the backend first:

```powershell
# from the repository root
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --app-dir backend
```

On the dashboard's **Settings** page choose **Hardware**. It resolves to
`http://localhost:8000` (or `NEXT_PUBLIC_LOCAL_API_URL` / `NEXT_PUBLIC_LOCAL_WS_URL`).

> A page served over HTTPS cannot open `ws://localhost`; browsers block it as
> mixed content. Hardware mode is for a locally served frontend
> (`http://localhost:3000`). Use **Online** mode for the deployed Vercel page.

### Point at the deployed backend (Online source mode)

The default API base is `https://neural-bridge-api.onrender.com`. No extra
environment variables are needed:

```powershell
.\.venv\Scripts\python -m nb_bridge
```

The deployed backend currently runs with `NEURAL_BRIDGE_MODE=mock`. In that mode
the mock generator and the bridge both publish, so frames interleave. Set
`NEURAL_BRIDGE_MODE=live` on Render to disable the mock generator and stream only
real device frames.

## Configuration

Every variable is optional. Defaults are safe for a synthetic run.

| Variable | Default | Meaning |
| --- | --- | --- |
| `NB_API_BASE` | `https://neural-bridge-api.onrender.com` | Backend base URL (`http(s)://…`) |
| `NB_BOARD` | `synthetic` | `synthetic`, `cyton`, `cyton_daisy` |
| `NB_SERIAL_PORT` | — | Required for `cyton*` (e.g. `COM3`) |
| `NB_DEVICE_NAME` | `openbci-cyton` | Name shown in `GET /devices` |
| `NB_PRESET` | `conversation` | Initial preset |
| `NB_UPDATE_HZ` | `5.0` | Frames per second (0.5–30) |
| `NB_WINDOW_SECONDS` | `2.0` | Rolling window used for the FFT (1–10 s) |
| `NB_EMA_ALPHA` | `0.2` | Smoothing factor for metrics (0–1, lower = smoother) |
| `NB_CALIBRATION_SECONDS` | `60.0` | Baseline capture; `0` disables |
| `NB_EMG_LOW_HZ` / `NB_EMG_HIGH_HZ` | `30` / `100` | Jaw-clench EMG band |
| `NB_INTENT_FOCUS_ENTER` | `0.85` | Focus threshold to enter a triggered state |
| `NB_INTENT_FOCUS_RELEASE` | `0.75` | Hysteresis release threshold |
| `NB_INTENT_SUSTAIN_SECONDS` | `1.5` | How long the threshold must hold |
| `NB_INTENT_COOLDOWN_SECONDS` | `4.0` | Minimum time between triggers |
| `NB_EMG_RATIO_THRESHOLD` | `2.5` | Clench detection threshold |
| `NB_EMG_FRAMES` | `2` | Consecutive frames above threshold |
| `NB_REQUEST_TIMEOUT` | `60.0` | Registration/health timeout (Render cold starts) |
| `NB_DEVICE_REGISTRATION_KEY` | — | Matches `DEVICE_REGISTRATION_KEY` when the backend protects enrollment |
| `NB_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

`NB_API_BASE` must include a scheme. Non-synthetic boards require
`NB_SERIAL_PORT`; the bridge exits with a clear error instead of guessing.

## Commands from the backend

The device socket also delivers commands. The bridge handles:

| Action | Payload | Effect |
| --- | --- | --- |
| `set_preset` (or `preset`) | `{"preset": "gaming"}` | Changes the frame's preset label |
| `calibrate` | `{"seconds": 30}` | Restarts baseline capture |
| `ping` | — | Logged at debug level |

Commands require the target device's API key, so browser preset buttons only
control the mock generator. Issue hardware commands from a trusted operator
tool that holds the device key; do not expose that key to the browser.

## Metrics and intent

- **Focus** = beta / (beta + theta)
- **Meditation** = alpha / (alpha + beta)
- **Attention** = beta / (beta + alpha + theta)

Band powers are **relative** (band ÷ 1–45 Hz total), which tolerates electrode
placement and session drift better than absolute power. A 60 s calibration maps
the user's own p5/p95 range to 0–1; `NB_CALIBRATION_SECONDS=0` uses fixed
clamps. Metrics are EMA-smoothed.

A flat or railed window is rejected by the artifact guard, so a disconnected
electrode does not produce a confident intent. A jaw clench is detected from
30–100 Hz RMS on T7/T8 (or the lateral fallback). Discrete intents use
threshold + hysteresis + sustain + cooldown, and set `triggered: true` for one
frame.

## Haptics bridge (output)

`nb_haptics` is the output-side counterpart to the EEG bridge. It registers as a
`haptics` device, waits for commands, and drives a mock or serial actuator:

```
dashboard Haptics panel
        │  POST /haptics/pulse  { intensity, duration_ms }
        ▼
FastAPI backend  ── selects a connected kind="haptics" device ──▶ device queue
        │
        ▼  {"type":"command","action":"pulse","payload":…}
hardware/nb_haptics  ── PULSE <intensity> <duration_ms> ──▶ actuator
```

The browser never receives a device API key. `POST /haptics/pulse` is the
operator path; it is CORS-limited and rate-limited per client IP
(`HAPTIC_RATE_LIMIT_SECONDS`, default `0.5`). It is still an unauthenticated
demo endpoint, so do not attach a powerful actuator to a public deployment.

### Mock quick start

With a backend running on `http://localhost:8000`:

```powershell
cd hardware
.\.venv\Scripts\python -m nb_haptics --check --pulse
.\.venv\Scripts\python -m nb_haptics
```

- `--check` validates the config, calls `/health`, and opens the driver.
- `--pulse` sends one test pulse (`0.60`, 250 ms); it can move a connected motor,
  so omit it when you only want a dry check.
- The default API base is `http://localhost:8000`. Override it with
  `--api-base` or `NB_HAPTICS_API_BASE`.
- The default actuator is `mock`: it logs pulses and records them in memory, so
  the full registration/command path works without hardware.

For the deployed backend:

```powershell
.\.venv\Scripts\python -m nb_haptics --api-base https://neural-bridge-api.onrender.com
```

If the backend sets `DEVICE_REGISTRATION_KEY`, export the same value as
`NB_HAPTICS_REGISTRATION_KEY` (or the shared `NB_DEVICE_REGISTRATION_KEY`).

On the dashboard:

1. For a local backend, open **Settings → Hardware → Save**.
2. For the deployed backend, choose **Online**.
3. The **Haptic output** panel polls `GET /devices`, shows the actuator, and sends
   the pulse. Demo mode has no backend, so the panel asks you to switch modes.

### Serial actuator

```powershell
$env:NB_HAPTICS_DRIVER="serial"
$env:NB_HAPTICS_SERIAL_PORT="COM4"   # check Device Manager
.\.venv\Scripts\python -m nb_haptics --check --pulse
.\.venv\Scripts\python -m nb_haptics
```

The reference sketch is
[`haptics_firmware/haptics_firmware.ino`](./haptics_firmware/haptics_firmware.ino).
Open it in the Arduino IDE, select the board and port, and upload it. Close the
Arduino Serial Monitor before starting the bridge; two programs cannot own the
same serial port.

> **Wiring safety:** never drive a vibration motor directly from a GPIO pin. Use
> a MOSFET or motor-driver module, a flyback diode across the motor, a separate
> motor supply, and a common ground. Check the motor's rated voltage and current.
> The sketch drives a DC ERM motor with PWM; an LRA needs a dedicated LRA driver.

The line protocol is:

| Command | Effect | Reply |
| --- | --- | --- |
| `PULSE 0.65 220` | Set PWM to 65% for 220 ms, then stop | `OK` |
| `STOP` | Stop immediately | `OK` |
| `PING` | Liveness check | `PONG` |

The bridge sends `PULSE` and reads one acknowledgement with a short timeout.
A missing acknowledgement is logged but does not mark an already-written pulse
as failed.

### Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `NB_HAPTICS_API_BASE` | `NB_API_BASE` or `http://localhost:8000` | Backend base URL |
| `NB_HAPTICS_DRIVER` | `mock` | `mock` or `serial` |
| `NB_HAPTICS_SERIAL_PORT` | — | Required for `serial` (e.g. `COM4`) |
| `NB_HAPTICS_BAUD` | `115200` | Serial baud rate |
| `NB_HAPTICS_DEVICE_NAME` | `haptic-hologram` | Name shown in `GET /devices` |
| `NB_HAPTICS_REQUEST_TIMEOUT` | `60.0` | Registration/health timeout |
| `NB_HAPTICS_REGISTRATION_KEY` | `NB_DEVICE_REGISTRATION_KEY` | Matches the backend secret |
| `NB_HAPTICS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

CLI overrides: `--api-base`, `--driver`, `--serial-port`, `--baud`,
`--device-name`, `--duration`, `--check`, `--pulse`.

### Backend endpoint

`POST /haptics/pulse` accepts:

```json
{ "intensity": 0.65, "duration_ms": 220, "device_id": "optional-id" }
```

`intensity` is `0..1`, `duration_ms` is `10..2000`. If `device_id` is omitted,
the first registered haptics device is used. Responses:

- `200 {"status":"queued","device":"…","name":"…"}`
- `404` no registered device (or the requested id is unknown)
- `409` device is registered but not connected
- `429` per-client cooldown or command queue saturation

The device must be connected over `WS /ws/devices/{id}`; the backend queues the
command and the bridge actuates it. The endpoint has no user authentication yet.

### Haptics verification

```powershell
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python ..\scripts\verify_pipeline.py
```

The unit suite covers config validation, pulse bounds, the mock driver, the
controller, and the serial line protocol against a fake port. The E2E script
also registers a haptics device, connects its socket, posts a pulse through the
browser-safe endpoint, and asserts the command arrives intact.

## Tests

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest tests -q
```

The suite covers signal helpers (including flat-signal and EMG guards), metrics
and calibration percentiles, the intent state machine, the exact wire format,
and the haptics config/driver/controller/serial protocol.

### Full end-to-end verification

From `hardware/` (the script needs this venv for `websockets`; it starts the
backend from the repository `.venv`):

```powershell
.\.venv\Scripts\python ..\scripts\verify_pipeline.py
```

It starts a throw-away backend in live mode on a free port and checks:

1. device registration and API-key auth,
2. `triggered` survives the device → backend → `/ws/telemetry` round trip,
3. a malformed frame is ignored without closing the socket,
4. commands are delivered to the device socket,
5. the device does not receive an echo of its own frames,
6. `POST /haptics/pulse` queues a command that reaches a connected haptics
   device with the exact intensity/duration,
7. the synthetic bridge produces ≥20 valid frames in 10 s with monotonic
   timestamps and all values in `[0, 1]`.

Exit code `0` and `E2E VERIFICATION PASSED` mean the contract is intact.

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `could not open cyton board on COM3` | GUI owns the port, wrong COM port, or dongle driver missing. Close the OpenBCI GUI, replug, check Device Manager. |
| `NB_SERIAL_PORT is required` | Set it for `cyton` / `cyton_daisy`. |
| `403` / `InvalidStatus` while registering | The backend restarted and lost its in-memory device registry. The client re-registers automatically on the next attempt. |
| `Waking server…` on the dashboard | Render free tier cold start (~50 s). The bridge and frontend both retry. |
| Frames stop, bridge logs a read error | Board unplugged or the dongle reset. The bridge exits instead of hammering a dead board; replug and restart. |
| Metrics pinned at 0 or 1 | Flat/railed signal, bad reference, or dry electrodes. Check impedances in the OpenBCI GUI first. |
| Trigger fires while talking | Lower `NB_EMG_RATIO_THRESHOLD` sensitivity by raising the threshold, or increase `NB_EMG_FRAMES`. |
| `could not open serial port COM4` | Close the Arduino Serial Monitor, check the port in Device Manager, or another program may own it. |
| Dashboard says “No haptic device connected” | Start `nb_haptics`, check it points at the same backend as the selected source, and confirm `GET /devices` lists a connected `haptics` device. |
| Haptics panel shows `429` | Wait for `HAPTIC_RATE_LIMIT_SECONDS` to elapse; repeated clicks are deliberately throttled. |
| Serial pulse sent but motor does not move | Check MOSFET/driver wiring, motor supply, common ground, and PWM pin; test with `--check --pulse`. |

## Safety

This is an experimental prototype, not a medical device. EEG-derived metrics are
noisy and user-specific. Never use it for diagnosis, treatment, or any safety-
critical decision. The Cyton is battery-powered; follow OpenBCI's instructions
for electrode placement and skin preparation.
