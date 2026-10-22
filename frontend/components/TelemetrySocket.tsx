"use client";

import { useEffect } from "react";
import { generateFrame } from "@/lib/simulator";
import { resolveSource } from "@/lib/source";
import { useBridgeStore } from "@/lib/store";
import type { PresetName, TelemetryFrame } from "@/lib/types";

// Backoff schedule (ms) used while the backend is asleep on Render's free tier.
const RECONNECT_DELAYS = [1000, 2000, 5000, 10000, 15000];
const DEMO_INTERVAL_MS = 180;

/**
 * Ask the backend to apply a preset.
 *
 * Mock deployments accept PUT /simulation/preset. Live deployments return 404
 * there, so we fall back to commanding the first connected EEG device, which
 * is what the hardware bridge listens for.
 */
async function pushPreset(apiUrl: string, preset: PresetName): Promise<void> {
  try {
    const response = await fetch(`${apiUrl}/simulation/preset/${preset}`, { method: "PUT" });
    if (response.ok) return;
  } catch {
    // Backend asleep or unreachable; try the device path below.
  }
  try {
    const response = await fetch(`${apiUrl}/devices`);
    if (!response.ok) return;
    const devices = (await response.json()) as Array<{ id: string; kind: string; connected: boolean }>;
    const target = devices.find((device) => device.connected && device.kind === "eeg");
    if (!target) return;
    await fetch(`${apiUrl}/devices/${target.id}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "set_preset", payload: { preset } })
    });
  } catch {
    // Best effort: a preset button must never throw.
  }
}

export function TelemetrySocket() {
  const source = useBridgeStore((state) => state.source);
  const preset = useBridgeStore((state) => state.preset);
  const setFrame = useBridgeStore((state) => state.setFrame);
  const setConnected = useBridgeStore((state) => state.setConnected);
  const setStatus = useBridgeStore((state) => state.setStatus);
  const hydrateSource = useBridgeStore((state) => state.hydrateSource);

  // Restore the saved option page choice once on the client.
  useEffect(() => {
    hydrateSource();
  }, [hydrateSource]);

  useEffect(() => {
    if (source === "demo") {
      setStatus("live");
      setConnected(true);
      setFrame(generateFrame(useBridgeStore.getState().preset));

      const timer = setInterval(() => {
        // Read the preset from the store each tick so switching modes is
        // instant without tearing down the interval.
        setFrame(generateFrame(useBridgeStore.getState().preset));
      }, DEMO_INTERVAL_MS);

      return () => {
        clearInterval(timer);
        setConnected(false);
      };
    }

    const { wsUrl } = resolveSource(source);

    // Browsers refuse ws:// from an https:// page. Fail fast and let the
    // settings page explain the workaround instead of retrying forever.
    if (
      typeof window !== "undefined" &&
      window.location.protocol === "https:" &&
      wsUrl.startsWith("ws://")
    ) {
      setConnected(false);
      setStatus("offline");
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");
      try {
        socket = new WebSocket(wsUrl);
      } catch {
        setConnected(false);
        setStatus("offline");
        return;
      }

      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
        setStatus("live");
      };

      socket.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data) as TelemetryFrame;
          if (typeof frame?.timestamp !== "number" || !frame.metrics || !frame.intent) return;
          setFrame(frame);
        } catch {
          // Ignore malformed frames instead of tearing down the socket.
        }
      };

      socket.onerror = () => socket?.close();

      socket.onclose = () => {
        setConnected(false);
        if (disposed) return;
        setStatus("connecting");
        const delay = RECONNECT_DELAYS[Math.min(attempt, RECONNECT_DELAYS.length - 1)];
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
      setConnected(false);
    };
  }, [source, setConnected, setFrame, setStatus]);

  // Keep the backend/device in sync with the preset buttons.
  useEffect(() => {
    if (source === "demo") return;
    const { apiUrl } = resolveSource(source);
    if (!apiUrl) return;
    void pushPreset(apiUrl, preset);
  }, [source, preset]);

  return null;
}
