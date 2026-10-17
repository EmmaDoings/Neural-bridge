"use client";

import { useEffect } from "react";
import { useBridgeStore } from "@/lib/store";
import type { TelemetryFrame } from "@/lib/types";

// Backoff schedule (ms) used while the backend is asleep on Render's free tier.
const RECONNECT_DELAYS = [1000, 2000, 5000, 10000, 15000];

export function TelemetrySocket() {
  const preset = useBridgeStore((state) => state.preset);
  const setFrame = useBridgeStore((state) => state.setFrame);
  const setConnected = useBridgeStore((state) => state.setConnected);
  const setStatus = useBridgeStore((state) => state.setStatus);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const baseUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/telemetry";

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");
      socket = new WebSocket(baseUrl);

      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
        setStatus("live");
      };

      socket.onmessage = (event) => {
        try {
          setFrame(JSON.parse(event.data) as TelemetryFrame);
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
    fetch(`${apiUrl}/simulation/preset/${preset}`, { method: "PUT" }).catch(() => {});

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
      setConnected(false);
      setStatus("offline");
    };
  }, [preset, setConnected, setFrame, setStatus]);

  return null;
}
