export type SourceMode = "demo" | "online" | "hardware";

export type SourceOption = {
  mode: SourceMode;
  label: string;
  shortLabel: string;
  tagline: string;
  description: string;
  requiresBackend: boolean;
  localOnly: boolean;
};

export const SOURCE_STORAGE_KEY = "neural-bridge:source";

export const SOURCE_OPTIONS: Record<SourceMode, SourceOption> = {
  demo: {
    mode: "demo",
    label: "Demo",
    shortLabel: "Demo",
    tagline: "Simulated signal",
    description:
      "A browser-side EEG simulator. Ideal for demos, offline use, and UI work. No backend and no hardware required.",
    requiresBackend: false,
    localOnly: false
  },
  online: {
    mode: "online",
    label: "Online",
    shortLabel: "Online",
    tagline: "Configured backend",
    description:
      "Streams from the configured backend — the deployed API in production. Use this when the hardware bridge is pushing into the cloud.",
    requiresBackend: true,
    localOnly: false
  },
  hardware: {
    mode: "hardware",
    label: "Hardware",
    shortLabel: "Hardware",
    tagline: "Local bridge",
    description:
      "Connects to a backend on this machine, fed by the BrainFlow bridge and your OpenBCI Cyton. Lowest latency, requires the local stack.",
    requiresBackend: true,
    localOnly: true
  }
};

const trimSlash = (value: string) => value.replace(/\/+$/, "");

const deployedApiUrl = () =>
  trimSlash(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

const deployedWsUrl = () =>
  process.env.NEXT_PUBLIC_WS_URL ?? `${deployedApiUrl().replace(/^http/, "ws")}/ws/telemetry`;

const localApiUrl = () =>
  trimSlash(process.env.NEXT_PUBLIC_LOCAL_API_URL ?? "http://localhost:8000");

const localWsUrl = () =>
  process.env.NEXT_PUBLIC_LOCAL_WS_URL ??
  `${localApiUrl().replace(/^http/, "ws")}/ws/telemetry`;

const withQuery = (url: string, query: string) => `${url}${url.includes("?") ? "&" : "?"}${query}`;

export type ResolvedSource = {
  mode: SourceMode;
  option: SourceOption;
  apiUrl: string;
  wsUrl: string;
};

export function resolveSource(mode: SourceMode): ResolvedSource {
  if (mode === "demo") {
    // Demo never touches the network; empty URLs make accidental use obvious.
    return { mode, option: SOURCE_OPTIONS[mode], apiUrl: "", wsUrl: "" };
  }
  if (mode === "hardware") {
    return {
      mode,
      option: SOURCE_OPTIONS[mode],
      apiUrl: localApiUrl(),
      // Hardware mode must not display the local mock generator when both
      // it and an EEG bridge are connected to the same backend.
      wsUrl: withQuery(localWsUrl(), "kind=eeg")
    };
  }
  return {
    mode,
    option: SOURCE_OPTIONS[mode],
    apiUrl: deployedApiUrl(),
    wsUrl: deployedWsUrl()
  };
}

export function isSourceMode(value: unknown): value is SourceMode {
  return value === "demo" || value === "online" || value === "hardware";
}

export function readStoredSource(): SourceMode {
  if (typeof window === "undefined") return "demo";
  try {
    const raw = window.localStorage.getItem(SOURCE_STORAGE_KEY);
    return isSourceMode(raw) ? raw : "demo";
  } catch {
    return "demo";
  }
}

export function writeStoredSource(mode: SourceMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SOURCE_STORAGE_KEY, mode);
  } catch {
    // Private mode / quota errors must not break the UI.
  }
}
