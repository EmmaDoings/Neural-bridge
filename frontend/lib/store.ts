import { create } from "zustand";
import { readStoredSource, writeStoredSource, type SourceMode } from "./source";
import type { PresetName, TelemetryFrame } from "./types";

export type ConnectionStatus = "connecting" | "live" | "offline";

type BridgeState = {
  frame: TelemetryFrame | null;
  preset: PresetName;
  source: SourceMode;
  connected: boolean;
  status: ConnectionStatus;
  setFrame: (frame: TelemetryFrame) => void;
  setPreset: (preset: PresetName) => void;
  setSource: (source: SourceMode) => void;
  hydrateSource: () => void;
  setConnected: (connected: boolean) => void;
  setStatus: (status: ConnectionStatus) => void;
};

export const useBridgeStore = create<BridgeState>((set, get) => ({
  frame: null,
  preset: "conversation",
  // Demo is the safe default: it works with or without a backend.
  source: "demo",
  connected: false,
  status: "connecting",
  setFrame: (frame) => set({ frame }),
  setPreset: (preset) => set({ preset }),
  setSource: (source) => {
    writeStoredSource(source);
    set({ source });
  },
  hydrateSource: () => {
    const stored = readStoredSource();
    if (stored !== get().source) {
      set({ source: stored });
    }
  },
  setConnected: (connected) => set({ connected }),
  setStatus: (status) => set({ status })
}));
