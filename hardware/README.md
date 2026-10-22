# Neural Bridge hardware bridge

Local Python process that turns an **OpenBCI Cyton** (or BrainFlow's synthetic
board) into telemetry frames for the Neural Bridge backend. It is a *client* of
the backend, not a second server for the browser.

```
OpenBCI Cyton ──USB dongle──▶ nb_bridge (BrainFlow + metrics + intent)
                                      │
                                      │  POST /devices
                                      │  WS /ws/devices/{id}?api_key=…
                                      ▼
                              FastAPI backend
                                      │  publish("*")
                                      ▼
                              WS /ws/telemetry
                                      │
                                      ▼
                              Next.js dashboard
```

The bridge registers itself, computes metrics and intent locally, and streams
one frame per `NB_UPDATE_HZ` over the existing device socket. Frames are
rebroadcast to every `/ws/telemetry` subscriber, which is what the dashboard
reads.

## What is verified

| Area | Status |
| --- | --- |
| BrainFlow 5.23.0 API (PSD, band powers, filters, EMG) | Verified empirically |
| Synthetic board end to end | Verified (41 frames in 10 s, valid ranges) |
| Backend contract (`triggered`, malformed frames, commands, no self-echo) | Verified |
| Unit tests | 32 passing |
| Real Cyton signal quality / impedances / EMG thresholds | **Pending hardware arrival** |

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

`requirements.txt` pins `brainflow==5.23.0` and `websockets==17.2`. Hardware
dependencies are **not** installed on Render; the deployed backend stays lightweight.

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

The dashboard's preset buttons send `set_preset` to the first connected `eeg`
device when the mock-only `PUT /simulation/preset/{preset}` endpoint is absent.

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

## Tests

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest tests -q
```

The suite covers signal helpers (including flat-signal and EMG guards), metrics
and calibration percentiles, the intent state machine, and the exact wire
format.

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
6. the synthetic bridge produces ≥20 valid frames in 10 s with monotonic
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

## Safety

This is an experimental prototype, not a medical device. EEG-derived metrics are
noisy and user-specific. Never use it for diagnosis, treatment, or any safety-
critical decision. The Cyton is battery-powered; follow OpenBCI's instructions
for electrode placement and skin preparation.
