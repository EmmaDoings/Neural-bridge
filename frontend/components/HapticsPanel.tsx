"use client";

import { useEffect, useState } from "react";
import type { DeviceInfo } from "@/lib/types";

type HapticsPanelProps = {
  apiUrl: string;
};

type PulseResponse = {
  status?: string;
  name?: string;
  detail?: unknown;
};

const POLL_MS = 5_000;
const REQUEST_TIMEOUT_MS = 10_000;

export function HapticsPanel({ apiUrl }: HapticsPanelProps) {
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [checked, setChecked] = useState(false);
  const [pollError, setPollError] = useState("");
  const [intensity, setIntensity] = useState(0.65);
  const [duration, setDuration] = useState(220);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!apiUrl) return;

    let cancelled = false;
    let inFlight = false;

    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      const controller = new AbortController();
      const timeout = window.setTimeout(
        () => controller.abort(),
        REQUEST_TIMEOUT_MS
      );
      try {
        const response = await fetch(`${apiUrl}/devices`, {
          signal: controller.signal,
          cache: "no-store"
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = (await response.json()) as DeviceInfo[];
        if (!cancelled) {
          setDevices(body.filter((device) => device.kind === "haptics"));
          setPollError("");
          setChecked(true);
        }
      } catch {
        if (!cancelled) {
          setDevices([]);
          setPollError(
            controller.signal.aborted
              ? "Haptics status timed out."
              : "Could not reach the haptics service."
          );
          setChecked(true);
        }
      } finally {
        inFlight = false;
        window.clearTimeout(timeout);
      }
    };

    void poll();
    const interval = window.setInterval(() => void poll(), POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [apiUrl]);

  const connected = devices.filter((device) => device.connected);
  const active = connected[0] ?? null;
  const registered = devices[0] ?? null;

  const status = !apiUrl
    ? "Switch to Online or Hardware"
    : !checked
      ? "Checking for an actuator…"
      : pollError
        ? "Haptics status unavailable"
        : active
          ? `${active.name} connected`
          : registered
            ? "Registered, waiting for the bridge"
            : "No haptic device connected";

  const pulse = async () => {
    if (!apiUrl) {
      setMessage("Choose Online or Hardware mode to use haptics.");
      return;
    }
    if (!active) {
      setMessage("Start the haptics bridge before sending a pulse.");
      return;
    }

    setSubmitting(true);
    setMessage("");
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      REQUEST_TIMEOUT_MS
    );
    try {
      const response = await fetch(`${apiUrl}/haptics/pulse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intensity,
          duration_ms: Math.round(duration)
        }),
        signal: controller.signal
      });
      let body: PulseResponse = {};
      try {
        body = (await response.json()) as PulseResponse;
      } catch {
        // Render/proxy errors can return HTML instead of JSON.
      }
      if (!response.ok) {
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      setMessage(
        body.name
          ? `Pulse queued for ${body.name}.`
          : "Pulse queued. Check the bridge log for delivery."
      );
    } catch (error) {
      if (controller.signal.aborted) {
        setMessage("The haptics service did not respond in time.");
      } else {
        setMessage(
          error instanceof Error
            ? error.message
            : "Unable to send the haptic pulse."
        );
      }
    } finally {
      window.clearTimeout(timeout);
      setSubmitting(false);
    }
  };

  return (
    <section
      className="space-y-4 rounded-[2rem] border border-white/10 bg-slate-950/70 p-5"
      aria-label="Haptic output"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
            Haptic output
          </p>
          <p className="mt-1 text-sm text-slate-300">
            Queue a bounded pulse for the connected hologram actuator.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-slate-400">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              active
                ? "bg-emerald-300 shadow-lg shadow-emerald-300/40"
                : "bg-slate-600"
            }`}
          />
          <span>{status}</span>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="space-y-2 text-xs uppercase tracking-[0.2em] text-slate-400">
          <span className="flex justify-between">
            <span>Intensity</span>
            <span className="text-cyan-200">{Math.round(intensity * 100)}%</span>
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={intensity}
            onChange={(event) => setIntensity(Number(event.target.value))}
            disabled={!apiUrl}
            className="w-full accent-cyan-300 disabled:opacity-40"
          />
        </label>
        <label className="space-y-2 text-xs uppercase tracking-[0.2em] text-slate-400">
          <span className="flex justify-between">
            <span>Duration</span>
            <span className="text-cyan-200">{duration} ms</span>
          </span>
          <input
            type="range"
            min={10}
            max={2000}
            step={10}
            value={duration}
            onChange={(event) => setDuration(Number(event.target.value))}
            disabled={!apiUrl}
            className="w-full accent-cyan-300 disabled:opacity-40"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void pulse()}
          disabled={!active || submitting}
          className="rounded-full bg-cyan-300 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Sending…" : "Send pulse"}
        </button>
        <span className="text-xs text-slate-500">
          The device key stays on the backend and bridge.
        </span>
      </div>
      {message && (
        <p className="text-sm text-slate-400" aria-live="polite">
          {message}
        </p>
      )}
    </section>
  );
}
