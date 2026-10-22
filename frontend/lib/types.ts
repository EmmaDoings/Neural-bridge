export type PresetName = "surgery" | "gaming" | "meditation" | "conversation" | "creative" | "navigation" | "idle";

export type TelemetryFrame = {
  timestamp: number;
  preset: PresetName;
  metrics: {
    focus: number;
    meditation: number;
    attention: number;
  };
  waves: {
    alpha: number;
    beta: number;
    theta: number;
  };
  intent: {
    label: string;
    confidence: number;
    action: string;
    color: string;
  };
  /** Device id that produced the frame (absent in client-side demo frames). */
  source?: string | null;
  /** One-frame pulse emitted when a discrete intent fires. */
  triggered?: boolean;
};
