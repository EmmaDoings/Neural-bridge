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

   - **`wss://` is required.** The page is served over `https://`, and browsers
     block insecure `ws://` connections (mixed content).
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

1. Open the Vercel URL — status should read **Live Stream** and the hologram
   should animate.
2. Switch presets; the color/scale of the hologram should change.
3. Let the backend sleep, reload the page, and confirm the status shows
   **Waking server…** until the stream returns.

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
