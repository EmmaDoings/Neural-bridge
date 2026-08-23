# Neural Bridge

Neural Bridge is a Brain-Computer Interface simulation prototype for closing the gap between reality, AI, and holograms. The goal is to make AI feel physically present: something you can talk to face-to-face, influence with thought, see as a hologram, and eventually touch through haptic or spatial interfaces.

## Product Vision

- One-on-one physical conversation with AI through a holographic interface
- Brain prompting: controlling AI through interpreted thought, focus, attention, and intent
- Touch-and-feel interaction with AI through future hologram and haptic feedback systems
- Real-life gaming experiences where AI, holograms, and player intent shape the environment
- Medical collaboration where a human and AI can operate together, with AI vision assisting surgery
- More realistic VR by combining cognitive input, spatial rendering, and multimodal AI feedback

## Stack

- Frontend: Next.js 14, TypeScript, Tailwind CSS, Zustand, Three.js
- Backend: FastAPI, async WebSockets, mock EEG telemetry presets
- DevOps: Docker Compose plus Bash and PowerShell bootstrap scripts

## Project Layout

```text
frontend/    Next.js interactive prototype
backend/     FastAPI telemetry and intent service
scripts/     Cross-platform startup helpers
```

## Quick Start

### Docker

```bash
docker compose up --build
```

Frontend: `http://localhost:3000`

Backend health: `http://localhost:8000/health`

### Local

```bash
./scripts/dev.sh
```

On Windows PowerShell:

```powershell
.\scripts\dev.ps1
```

## Current Prototype Scope

- Mock Mode Simulator with seven cognitive presets
- REST endpoint for current telemetry
- WebSocket stream for low-latency cognitive frames
- Deterministic intent parser standing in for a future Gemini orchestration client
- Reactive 3D hologram that changes color, scale, rotation, and pulse by cognitive state
- Interactive hologram: drag to rotate, scroll/pinch to zoom, tap to switch modes
- Device bus: register devices, push telemetry with API-key auth, broadcast routing, and command delivery to connected devices over `/ws/devices/{id}`

## Next Milestones

- Add physical EEG adapters for Muse or Emotiv streams
- Replace deterministic parser with Gemini-backed orchestration
- Add microphone STT and Pygame TTS loop
- Add Looking Glass or stereoscopic display mode
