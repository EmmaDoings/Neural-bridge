import { create } from "zustand";
import type { PresetName, TelemetryFrame } from "./types";

export type ConnectionStatus = "connecting" | "live" | "offline";

type BridgeState = {
  frame: TelemetryFrame | null;
  preset: PresetName;
  connected: boolean;
  status: ConnectionStatus;
  setFrame: (frame: TelemetryFrame) => void;
  setPreset: (preset: PresetName) => void;
  setConnected: (connected: boolean) => void;
  setStatus: (status: ConnectionStatus) => void;
};

export const useBridgeStore = create<BridgeState>((set) => ({
  frame: null,
  preset: "conversation",
  connected: false,
  status: "connecting",
  setFrame: (frame) => set({ frame }),
  setPreset: (preset) => set({ preset }),
  setConnected: (connected) => set({ connected }),
  setStatus: (status) => set({ status })
}));
