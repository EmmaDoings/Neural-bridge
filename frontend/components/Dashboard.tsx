"use client";

import { Hologram } from "./Hologram";
import { TelemetrySocket } from "./TelemetrySocket";
import { useBridgeStore } from "@/lib/store";
import type { PresetName } from "@/lib/types";

const presets: PresetName[] = ["surgery", "gaming", "meditation", "conversation", "creative", "navigation", "idle"];

function Meter({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs uppercase tracking-[0.3em] text-slate-400">
        <span>{label}</span>
        <span>{Math.round(value * 100)}%</span>
      </div>
      <div className="h-2 rounded-full bg-slate-800">
        <div className="h-full rounded-full bg-cyan-300 shadow-lg shadow-cyan-300/40" style={{ width: `${value * 100}%` }} />
      </div>
    </div>
  );
}

export function Dashboard() {
  const frame = useBridgeStore((state) => state.frame);
  const preset = useBridgeStore((state) => state.preset);
  const connected = useBridgeStore((state) => state.connected);
  const setPreset = useBridgeStore((state) => state.setPreset);

  return (
    <main className="mx-auto grid min-h-screen max-w-7xl gap-8 px-5 py-6 md:grid-cols-[0.95fr_1.05fr] md:px-8 md:py-10">
      <TelemetrySocket />
      <section className="flex flex-col justify-between gap-8 rounded-[2rem] border border-white/10 bg-white/[0.04] p-6 backdrop-blur md:p-8">
        <div className="space-y-6">
          <div className="flex items-center justify-between gap-4">
            <span className="rounded-full border border-cyan-300/30 px-3 py-1 text-xs uppercase tracking-[0.35em] text-cyan-200">Neural Bridge</span>
            <span className={connected ? "text-sm text-emerald-300" : "text-sm text-rose-300"}>{connected ? "Live Stream" : "Disconnected"}</span>
          </div>
          <div className="space-y-4">
            <h1 className="text-4xl font-semibold tracking-[-0.04em] text-white md:text-6xl">Pure cognitive execution layer.</h1>
            <p className="max-w-2xl text-base leading-7 text-slate-300 md:text-lg">
              Mock EEG telemetry is interpreted as intent and reflected through a real-time holographic control surface.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {presets.map((item) => (
              <button
                key={item}
                onClick={() => setPreset(item)}
                className={`rounded-full px-4 py-2 text-sm capitalize transition ${
                  preset === item ? "bg-cyan-300 text-slate-950" : "bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-5 rounded-3xl bg-slate-950/70 p-5">
          <Meter label="Focus" value={frame?.metrics.focus ?? 0} />
          <Meter label="Meditation" value={frame?.metrics.meditation ?? 0} />
          <Meter label="Attention" value={frame?.metrics.attention ?? 0} />
        </div>
      </section>

      <section className="space-y-5">
        <Hologram />
        <div className="grid gap-4 rounded-[2rem] border border-white/10 bg-slate-950/70 p-5 md:grid-cols-3">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Intent</p>
            <p className="mt-2 text-xl text-white">{frame?.intent.label.replaceAll("_", " ") ?? "Awaiting signal"}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Confidence</p>
            <p className="mt-2 text-xl text-white">{Math.round((frame?.intent.confidence ?? 0) * 100)}%</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Action</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">{frame?.intent.action ?? "maintain passive telemetry loop"}</p>
          </div>
        </div>
      </section>
    </main>
  );
}
