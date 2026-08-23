"use client";

import { useEffect } from "react";
import { useBridgeStore } from "@/lib/store";
import type { TelemetryFrame } from "@/lib/types";

export function TelemetrySocket() {
  const preset = useBridgeStore((state) => state.preset);
  const setFrame = useBridgeStore((state) => state.setFrame);
  const setConnected = useBridgeStore((state) => state.setConnected);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${apiUrl}/simulation/preset/${preset}`, { method: "PUT" }).catch(() => {});

    const baseUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/telemetry";
    const socket = new WebSocket(baseUrl);

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);
    socket.onmessage = (event) => setFrame(JSON.parse(event.data) as TelemetryFrame);

    return () => socket.close();
  }, [preset, setConnected, setFrame]);

  return null;
}
