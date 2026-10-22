import type { PresetName, TelemetryFrame } from "./types";

// Faithful port of backend/app/simulator.py so the Demo source looks exactly
// like the server-side mock. Keep the tables and thresholds in sync.

type PresetSnapshot = {
  metrics: { focus: number; meditation: number; attention: number };
  waves: { alpha: number; beta: number; theta: number };
};

const PRESETS: Record<PresetName, PresetSnapshot> = {
  surgery: {
    metrics: { focus: 0.92, meditation: 0.22, attention: 0.95 },
    waves: { alpha: 0.26, beta: 0.88, theta: 0.18 }
  },
  gaming: {
    metrics: { focus: 0.84, meditation: 0.18, attention: 0.9 },
    waves: { alpha: 0.22, beta: 0.82, theta: 0.24 }
  },
  meditation: {
    metrics: { focus: 0.42, meditation: 0.94, attention: 0.58 },
    waves: { alpha: 0.88, beta: 0.18, theta: 0.7 }
  },
  conversation: {
    metrics: { focus: 0.64, meditation: 0.52, attention: 0.72 },
    waves: { alpha: 0.52, beta: 0.56, theta: 0.42 }
  },
  creative: {
    metrics: { focus: 0.72, meditation: 0.66, attention: 0.68 },
    waves: { alpha: 0.74, beta: 0.48, theta: 0.62 }
  },
  navigation: {
    metrics: { focus: 0.78, meditation: 0.34, attention: 0.86 },
    waves: { alpha: 0.36, beta: 0.74, theta: 0.32 }
  },
  idle: {
    metrics: { focus: 0.24, meditation: 0.58, attention: 0.28 },
    waves: { alpha: 0.58, beta: 0.2, theta: 0.64 }
  }
};

function parseIntent(
  metrics: PresetSnapshot["metrics"],
  waves: PresetSnapshot["waves"]
): TelemetryFrame["intent"] {
  if (metrics.focus > 0.86 && metrics.attention > 0.86) {
    return {
      label: "precision_execution",
      confidence: 0.93,
      action: "stabilize high-fidelity control surface",
      color: "#38bdf8"
    };
  }
  if (metrics.meditation > 0.85 && waves.alpha > 0.75) {
    return {
      label: "calm_space",
      confidence: 0.9,
      action: "dim environment and reduce motion",
      color: "#a78bfa"
    };
  }
  if (waves.theta > 0.58 && metrics.focus > 0.65) {
    return {
      label: "creative_synthesis",
      confidence: 0.84,
      action: "expand ideation workspace",
      color: "#f59e0b"
    };
  }
  if (metrics.attention > 0.8) {
    return {
      label: "spatial_navigation",
      confidence: 0.82,
      action: "highlight next target path",
      color: "#22c55e"
    };
  }
  return {
    label: "ambient_monitoring",
    confidence: 0.68,
    action: "maintain passive telemetry loop",
    color: "#94a3b8"
  };
}

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

function jitter(value: number, phase: number): number {
  const drift = Math.sin((Date.now() / 1000) * 1.7 + phase) * 0.04;
  const noise = (Math.random() - 0.5) * 0.05;
  return clamp01(value + drift + noise);
}

export function generateFrame(preset: PresetName): TelemetryFrame {
  const base = PRESETS[preset];
  const metrics = {
    focus: jitter(base.metrics.focus, 0),
    meditation: jitter(base.metrics.meditation, 2),
    attention: jitter(base.metrics.attention, 4)
  };
  const waves = {
    alpha: jitter(base.waves.alpha, 1),
    beta: jitter(base.waves.beta, 3),
    theta: jitter(base.waves.theta, 5)
  };

  return {
    timestamp: Date.now() / 1000,
    preset,
    metrics,
    waves,
    intent: parseIntent(metrics, waves),
    source: "demo",
    triggered: false
  };
}
