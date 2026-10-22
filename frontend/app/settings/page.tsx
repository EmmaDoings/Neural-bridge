"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { resolveSource, SOURCE_OPTIONS, type SourceMode } from "@/lib/source";
import { useBridgeStore } from "@/lib/store";

type TestState =
  | { status: "idle" }
  | { status: "testing" }
  | { status: "ok"; message: string }
  | { status: "error"; message: string };

const ORDER: SourceMode[] = ["demo", "online", "hardware"];

// Stable no-op subscription: the page protocol never changes at runtime.
const subscribeToProtocol = () => () => {};

export default function SettingsPage() {
  const router = useRouter();
  const source = useBridgeStore((state) => state.source);
  const setSource = useBridgeStore((state) => state.setSource);
  const hydrateSource = useBridgeStore((state) => state.hydrateSource);

  // `draft` is the unsaved choice; null means "follow the saved source".
  const [draft, setDraft] = useState<SourceMode | null>(null);
  const selected = draft ?? source;
  const [test, setTest] = useState<TestState>({ status: "idle" });
  const isHttps = useSyncExternalStore(
    subscribeToProtocol,
    () => window.location.protocol === "https:",
    () => false
  );

  useEffect(() => {
    hydrateSource();
  }, [hydrateSource]);

  const resolved = useMemo(() => resolveSource(selected), [selected]);
  const mixedContent = isHttps && selected === "hardware";

  const choose = (mode: SourceMode) => {
    setDraft(mode);
    setTest({ status: "idle" });
  };

  const testConnection = async () => {
    if (!resolved.option.requiresBackend) return;
    setTest({ status: "testing" });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(`${resolved.apiUrl}/health`, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = (await response.json()) as { status?: string; mode?: string };
      setTest({
        status: "ok",
        message: `Reachable — status: ${body.status ?? "unknown"}, backend mode: ${body.mode ?? "unknown"}`
      });
    } catch (error) {
      const message =
        error instanceof DOMException && error.name === "AbortError"
          ? "Timed out after 30s. On Render's free tier the server may still be waking."
          : error instanceof TypeError
            ? `Could not reach ${resolved.apiUrl}. Is the backend running, and does CORS_ORIGINS allow this page's origin?`
            : error instanceof Error
              ? error.message
              : "Unreachable";
      setTest({ status: "error", message });
    } finally {
      clearTimeout(timeout);
    }
  };

  const apply = () => {
    setSource(selected);
    router.push("/");
  };

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-5 py-8 md:px-8 md:py-12">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-cyan-200">Neural Bridge</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-white md:text-5xl">Choose your signal source.</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400 md:text-base">
            Demo runs entirely in your browser. Online uses the deployed backend. Hardware talks to the OpenBCI bridge on your
            machine. Your choice is stored in this browser.
          </p>
        </div>
        <Link
          href="/"
          className="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:border-cyan-300/40 hover:text-cyan-200"
        >
          Back to dashboard
        </Link>
      </div>

      <div role="radiogroup" aria-label="Signal source" className="grid gap-4 md:grid-cols-3">
        {ORDER.map((mode) => {
          const option = SOURCE_OPTIONS[mode];
          const active = selected === mode;
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => choose(mode)}
              className={`rounded-[1.75rem] border p-5 text-left transition ${
                active
                  ? "border-cyan-300/60 bg-cyan-300/[0.07] shadow-lg shadow-cyan-400/10"
                  : "border-white/10 bg-slate-950/60 hover:border-white/25"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase tracking-[0.3em] text-slate-400">{option.label}</span>
                <span
                  aria-hidden
                  className={`h-3 w-3 rounded-full border ${
                    active ? "border-cyan-300 bg-cyan-300" : "border-slate-600"
                  }`}
                />
              </div>
              <p className="mt-4 text-lg text-white">{option.tagline}</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">{option.description}</p>
            </button>
          );
        })}
      </div>

      <section className="mt-6 space-y-4 rounded-[1.75rem] border border-white/10 bg-slate-950/60 p-5 md:p-6">
        <h2 className="text-xs uppercase tracking-[0.3em] text-slate-500">Connection</h2>

        {selected === "demo" ? (
          <p className="text-sm leading-6 text-slate-300">
            No network calls. Frames are generated in this tab at roughly 5.5 Hz using the same presets and intent rules as the
            backend simulator.
          </p>
        ) : (
          <dl className="grid gap-3 text-sm">
            <div className="grid gap-1 md:grid-cols-[140px_1fr] md:items-center">
              <dt className="text-slate-500">API</dt>
              <dd className="break-all font-mono text-slate-200">{resolved.apiUrl}</dd>
            </div>
            <div className="grid gap-1 md:grid-cols-[140px_1fr] md:items-center">
              <dt className="text-slate-500">WebSocket</dt>
              <dd className="break-all font-mono text-slate-200">{resolved.wsUrl}</dd>
            </div>
          </dl>
        )}

        <p className="text-xs leading-5 text-slate-500">
          These URLs come from <code className="text-slate-300">NEXT_PUBLIC_*</code> variables, which Next.js inlines at build
          time. Change them in Vercel (or <code className="text-slate-300">.env</code>) and redeploy.
        </p>

        {mixedContent && (
          <div className="rounded-2xl border border-amber-300/30 bg-amber-300/[0.06] p-4 text-sm leading-6 text-amber-100">
            <strong className="font-semibold">HTTPS blocks local WebSockets.</strong> This page is served over HTTPS, so the
            browser will refuse <code>ws://localhost</code>. Run the frontend locally for Hardware mode, or keep the bridge
            pointed at the deployed backend and use Online mode.
          </div>
        )}

        {resolved.option.requiresBackend && (
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={testConnection}
              disabled={test.status === "testing"}
              className="rounded-full bg-slate-800 px-4 py-2 text-sm text-slate-200 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {test.status === "testing" ? "Testing…" : "Test connection"}
            </button>
            {test.status === "ok" && <span className="text-sm text-emerald-300">{test.message}</span>}
            {test.status === "error" && <span className="text-sm text-rose-300">{test.message}</span>}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-white/5 pt-4">
          <button
            type="button"
            onClick={apply}
            className="rounded-full bg-cyan-300 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-200"
          >
            Save &amp; open dashboard
          </button>
          <span className="text-xs text-slate-500">
            Current: <span className="text-slate-300">{SOURCE_OPTIONS[source].label}</span>
          </span>
        </div>
      </section>

      <details className="mt-6 rounded-[1.75rem] border border-white/10 bg-slate-950/60 p-5 md:p-6">
        <summary className="cursor-pointer text-sm text-slate-200">Hardware setup (OpenBCI Cyton)</summary>
        <div className="mt-4 space-y-4 text-sm leading-6 text-slate-400">
          <p>
            The bridge is a client of the backend. It registers a device, reads the board, computes metrics and streams frames
            over the existing device socket.
          </p>
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              Plug in the Cyton dongle and find its port (for example <code className="text-slate-200">COM3</code>).
            </li>
            <li>
              In <code className="text-slate-200">hardware/</code>, verify the board and the backend:
              <pre className="mt-2 overflow-x-auto rounded-xl bg-black/40 p-3 text-xs text-slate-300">
{`.venv\\Scripts\\python -m nb_bridge --check`}
              </pre>
            </li>
            <li>
              Stream to the deployed backend (Online mode):
              <pre className="mt-2 overflow-x-auto rounded-xl bg-black/40 p-3 text-xs text-slate-300">
{`$env:NB_BOARD="cyton"
$env:NB_SERIAL_PORT="COM3"
.venv\\Scripts\\python -m nb_bridge`}
              </pre>
            </li>
            <li>
              For Hardware mode, also run the backend locally and point the bridge at it:
              <pre className="mt-2 overflow-x-auto rounded-xl bg-black/40 p-3 text-xs text-slate-300">
{`$env:NB_API_BASE="http://localhost:8000"
.venv\\Scripts\\python -m nb_bridge`}
              </pre>
            </li>
          </ol>
          <p>
            Without a board, leave <code className="text-slate-200">NB_BOARD=synthetic</code> (the default) to exercise the
            entire pipeline.
          </p>
        </div>
      </details>
    </main>
  );
}
