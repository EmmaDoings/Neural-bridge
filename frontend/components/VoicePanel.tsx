"use client";

import { useEffect, useRef, useState } from "react";
import type { TelemetryFrame } from "@/lib/types";

type RecognitionEvent = Event & {
  results: {
    [index: number]:
      | { [index: number]: { transcript: string } | undefined }
      | undefined;
  };
};

type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};

type RecognitionConstructor = new () => Recognition;

type VoicePanelProps = {
  apiUrl: string;
  frame: TelemetryFrame | null;
};

export function VoicePanel({ apiUrl, frame }: VoicePanelProps) {
  const recognitionRef = useRef<Recognition | null>(null);
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [reply, setReply] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const browserWindow = window as typeof window & {
      SpeechRecognition?: RecognitionConstructor;
      webkitSpeechRecognition?: RecognitionConstructor;
    };
    const Constructor = browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition;
    if (!Constructor) return;

    const recognition = new Constructor();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) setText(transcript);
      setListening(false);
    };
    recognition.onerror = () => {
      setListening(false);
      setMessage("Voice capture was unavailable. You can type instead.");
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;

    return () => {
      try {
        recognition.stop();
      } catch {
        // The recognizer may already be idle; there is nothing to stop.
      }
    };
  }, []);

  const speak = (value: string) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(value));
  };

  const submit = async () => {
    const transcript = text.trim();
    if (!frame) {
      setMessage("Wait for a telemetry frame before asking Neural Bridge.");
      return;
    }
    if (!apiUrl) {
      setMessage("Choose Online or Hardware mode to use the response service.");
      return;
    }
    if (!transcript && !frame.triggered) {
      setMessage("Say or type a request, or wait for a triggered intent.");
      return;
    }

    setSubmitting(true);
    setMessage("");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    try {
      const response = await fetch(`${apiUrl}/intent/respond`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frame, transcript: transcript || undefined }),
        signal: controller.signal
      });
      let body: { text?: string; detail?: unknown; provider?: string } = {};
      try {
        body = (await response.json()) as typeof body;
      } catch {
        // A proxy or cold-start error may return HTML instead of JSON.
      }
      if (!response.ok || !body.text) {
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : `HTTP ${response.status}`;
        throw new Error(detail);
      }
      setReply(body.text);
      setMessage(body.provider === "fallback" ? "Using the local fallback response." : "Gemini response received.");
      speak(body.text);
    } catch (error) {
      if (controller.signal.aborted) {
        setMessage("The response timed out. Check the backend and try again.");
      } else {
        setMessage(error instanceof Error ? error.message : "Unable to get a response.");
      }
    } finally {
      window.clearTimeout(timeout);
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-3 rounded-[2rem] border border-white/10 bg-slate-950/70 p-5" aria-label="Voice and typed assistant">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Neural response</p>
          <p className="mt-1 text-sm text-slate-300">Speak or type a request with the current telemetry as context.</p>
        </div>
        <button
          type="button"
          onClick={() => {
            const recognition = recognitionRef.current;
            if (!recognition) {
              setMessage("Voice capture is unavailable in this browser. You can type instead.");
              return;
            }
            try {
              if (listening) {
                recognition.stop();
                setListening(false);
              } else {
                recognition.start();
                setListening(true);
                setMessage("");
              }
            } catch {
              setListening(false);
              setMessage("Voice capture could not start. You can type instead.");
            }
          }}
          aria-pressed={listening}
          className="shrink-0 rounded-full border border-cyan-300/40 px-3 py-1.5 text-xs text-cyan-100 transition hover:bg-cyan-300/10"
        >
          {listening ? "Stop listening" : "Use microphone"}
        </button>
      </div>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={3}
        maxLength={1000}
        placeholder="Ask about the current state…"
        className="w-full resize-y rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-600 focus:border-cyan-300/50"
      />
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={submitting || !frame}
          className="rounded-full bg-cyan-300 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Thinking…" : "Ask Neural Bridge"}
        </button>
        <span className="text-xs text-slate-500">Voice support depends on your browser; typed input always works.</span>
      </div>
      {message && <p className="text-sm text-slate-400" aria-live="polite">{message}</p>}
      {reply && <p className="rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.05] p-4 text-sm leading-6 text-cyan-50">{reply}</p>}
    </section>
  );
}
