# Deploying Neural Bridge for $0

Host the **FastAPI + WebSocket backend on Render** (free web service) and the
**Next.js 3D frontend on Vercel** (Hobby). No credit card required.

```
Browser ──https──▶ Vercel (Next.js)  ──wss──▶ Render (FastAPI /ws/telemetry)
```

Deploy in this order so you always have the URL you need for the next step:

1. Push the repo to GitHub.
2. Deploy the backend on Render → copy its URL.
3. Deploy the frontend on Vercel with that URL.
4. Point the backend's `CORS_ORIGINS` at the Vercel URL.

---

## 1. Backend → Render

This repo ships a [`render.yaml`](./render.yaml) Blueprint, so you can skip most
of the manual setup.

1. Render Dashboard → **New** → **Blueprint** → select this repository.
2. Render reads `render.yaml` and asks for the two secrets marked `sync: false`:
   - **`CORS_ORIGINS`** → leave blank for now, set it in step 4.
   - **`CORS_ORIGIN_REGEX`** → optional, e.g. `https://.*\.vercel\.app` to allow
     Vercel preview deployments.
3. Apply. Render builds `backend/` and starts:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
4. Verify:
   - `https://<service>.onrender.com/health` → `{"status":"ok","mode":"mock"}`
   - `wss://<service>.onrender.com/ws/telemetry` streams telemetry frames.

**Prefer clicking through manually?** New → **Web Service** with:

| Setting          | Value                                              |
| ---------------- | -------------------------------------------------- |
| Root Directory   | `backend`                                          |
| Runtime          | Python 3                                           |
| Build Command    | `pip install -r requirements.txt`                  |
| Start Command    | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check     | `/health`                                          |
| Instance Type    | Free                                               |
| `PYTHON_VERSION` | `3.13.5`                                           |
| `NEURAL_BRIDGE_MODE` | `mock`                                         |

> `NEURAL_BRIDGE_MODE=mock` generates frames inside the backend. For an
> **Online**-mode setup fed by a real bridge, set it to `live`; otherwise the mock
> generator and the hardware bridge both publish and the frames interleave.

> The start command must use `$PORT`. Render injects it, and a hardcoded `8000`
> fails the health check. `backend/Dockerfile` now honors `$PORT` too, so a
> Docker-based deploy works as well.

### What the free tier means here

- 512 MB RAM, shared CPU — plenty for the mock generator.
- The service **sleeps after ~15 minutes of inactivity** and cold-starts in ~50 s.
- State on the device bus is **in-memory**, so devices and API keys reset on every
  restart. Free tier is single-instance (do not add `--workers`).
- The frontend handles the cold start: `components/TelemetrySocket.tsx` retries
  with backoff and shows "Waking server…" instead of a dead hologram.
- Optional: a keep-alive pinger (UptimeRobot, cron-job.org) hitting `/health`
  every 10–14 min keeps the instance warm and hides most cold starts.

---

## 2. Frontend → Vercel

1. Vercel → **Add New** → **Project** → import the same repository.
2. **Root Directory:** `frontend` (framework auto-detects Next.js; leave the
   build/output defaults).
3. **Environment Variables** — add these for Production *and* Preview:

   | Name                   | Value                                                     |
   | ---------------------- | --------------------------------------------------------- |
   | `NEXT_PUBLIC_API_URL`  | `https://<service>.onrender.com`                          |
   | `NEXT_PUBLIC_WS_URL`   | `wss://<service>.onrender.com/ws/telemetry`               |
   | `NEXT_PUBLIC_LOCAL_API_URL` (optional) | `http://localhost:8000`                    |
   | `NEXT_PUBLIC_LOCAL_WS_URL` (optional)  | `ws://localhost:8000/ws/telemetry`         |

   - **`wss://` is required.** The page is served over `https://`, and browsers
     block insecure `ws://` connections (mixed content).
   - The `NEXT_PUBLIC_LOCAL_*` variables only affect the **Hardware** option.
     They default to `localhost:8000`, so production can omit them. Hardware
     mode cannot work from the HTTPS Vercel page anyway; use it with
     `http://localhost:3000`.
   - `NEXT_PUBLIC_*` values are inlined at **build time**, so changing them
     requires a **Redeploy** (Deployments → ⋯ → Redeploy).
4. Deploy and note the URL, e.g. `https://neural-bridge.vercel.app`.

See [`frontend/.env.example`](./frontend/.env.example) for local defaults.

---

## 3. Close the loop (CORS)

In Render → your service → **Environment**, set:

```
CORS_ORIGINS=https://neural-bridge.vercel.app
```

Redeploy the backend. The API runs with `allow_credentials=True`, which **cannot**
be combined with `*`, so the exact origin (or the `CORS_ORIGIN_REGEX`, which this
repo now supports) is required.

---

## 4. Verify end to end

1. Open the Vercel URL. **Demo** is the default source: the hologram animates
   with no backend calls.
2. Open **Settings → Online → Test connection**. It should report
   `Reachable — status: ok, backend mode: mock`. Save; the status should read
   **Live Stream**.
3. Switch presets; the color/scale of the hologram should change.
4. Let the backend sleep, reload the page, and confirm the status shows
   **Waking server…** until the stream returns.
5. Open **Settings → Hardware** to see the local endpoints and the HTTPS
   mixed-content warning (only shown when the page is served over HTTPS).

---

## 5. Hardware bridge (optional, local machine)

The bridge is **not** deployed to Render. It runs next to the Cyton and connects
to either the deployed backend or a local one. See
[`hardware/README.md`](./hardware/README.md) for the full guide.

```powershell
cd hardware
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Synthetic board -> deployed backend (safe default)
.\.venv\Scripts\python -m nb_bridge --check
.\.venv\Scripts\python -m nb_bridge

# Real Cyton -> deployed backend
$env:NB_BOARD="cyton"
$env:NB_SERIAL_PORT="COM3"
.\.venv\Scripts\python -m nb_bridge
```

To use the deployed backend as a live (non-mock) source:

1. Render → Environment → set `NEURAL_BRIDGE_MODE=live`.
2. Restart/redeploy the backend.
3. Run the bridge with `NB_API_BASE=https://<service>.onrender.com` (the default).
4. On the Vercel site choose **Online**. Frames now originate from the bridge.

The device registry is in-memory, so a Render restart invalidates the bridge's
key. The bridge re-registers automatically on HTTP 403 or close code `4401`.

### Verify the bridge contract

```powershell
cd hardware
.\.venv\Scripts\python ..\scripts\verify_pipeline.py
```

This starts a throw-away backend in live mode and checks registration,
`triggered` propagation, malformed-frame tolerance, command delivery, no
self-echo, and a valid synthetic stream.

---

## Secrets

- `NEXT_PUBLIC_*` values ship to every browser — treat them as public. The device
  API keys returned by `POST /devices` are the real credentials and stay in memory.
- Generate backend-only secrets on Render with:
  ```
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

## Cost recap

| Service | Plan   | Cost |
| ------- | ------ | ---- |
| Render  | Free   | $0   |
| Vercel  | Hobby  | $0   |

The trade-off is cold starts and in-memory state — expected for a $0 prototype.
