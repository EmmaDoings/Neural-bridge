import { create } from "zustand";
import type { PresetName, TelemetryFrame } from "./types";

type BridgeState = {
  frame: TelemetryFrame | null;
  preset: PresetName;
  connected: boolean;
  setFrame: (frame: TelemetryFrame) => void;
  setPreset: (preset: PresetName) => void;
  setConnected: (connected: boolean) => void;
};

export const useBridgeStore = create<BridgeState>((set) => ({
  frame: null,
  preset: "conversation",
  connected: false,
  setFrame: (frame) => set({ frame }),
  setPreset: (preset) => set({ preset }),
  setConnected: (connected) => set({ connected })
}));
