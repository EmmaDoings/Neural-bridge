import math
import random
import time

from app.models import CognitiveMetrics, Intent, PresetName, TelemetryFrame, WaveBands


PRESETS: dict[PresetName, tuple[CognitiveMetrics, WaveBands]] = {
    "surgery": (CognitiveMetrics(focus=0.92, meditation=0.22, attention=0.95), WaveBands(alpha=0.26, beta=0.88, theta=0.18)),
    "gaming": (CognitiveMetrics(focus=0.84, meditation=0.18, attention=0.9), WaveBands(alpha=0.22, beta=0.82, theta=0.24)),
    "meditation": (CognitiveMetrics(focus=0.42, meditation=0.94, attention=0.58), WaveBands(alpha=0.88, beta=0.18, theta=0.7)),
    "conversation": (CognitiveMetrics(focus=0.64, meditation=0.52, attention=0.72), WaveBands(alpha=0.52, beta=0.56, theta=0.42)),
    "creative": (CognitiveMetrics(focus=0.72, meditation=0.66, attention=0.68), WaveBands(alpha=0.74, beta=0.48, theta=0.62)),
    "navigation": (CognitiveMetrics(focus=0.78, meditation=0.34, attention=0.86), WaveBands(alpha=0.36, beta=0.74, theta=0.32)),
    "idle": (CognitiveMetrics(focus=0.24, meditation=0.58, attention=0.28), WaveBands(alpha=0.58, beta=0.2, theta=0.64)),
}


def parse_intent(metrics: CognitiveMetrics, waves: WaveBands) -> Intent:
    if metrics.focus > 0.86 and metrics.attention > 0.86:
        return Intent(label="precision_execution", confidence=0.93, action="stabilize high-fidelity control surface", color="#38bdf8")
    if metrics.meditation > 0.85 and waves.alpha > 0.75:
        return Intent(label="calm_space", confidence=0.9, action="dim environment and reduce motion", color="#a78bfa")
    if waves.theta > 0.58 and metrics.focus > 0.65:
        return Intent(label="creative_synthesis", confidence=0.84, action="expand ideation workspace", color="#f59e0b")
    if metrics.attention > 0.8:
        return Intent(label="spatial_navigation", confidence=0.82, action="highlight next target path", color="#22c55e")
    return Intent(label="ambient_monitoring", confidence=0.68, action="maintain passive telemetry loop", color="#94a3b8")


def _jitter(value: float, phase: float) -> float:
    drift = math.sin(time.time() * 1.7 + phase) * 0.04
    noise = random.uniform(-0.025, 0.025)
    return max(0, min(1, value + drift + noise))


def generate_frame(preset: PresetName) -> TelemetryFrame:
    base_metrics, base_waves = PRESETS[preset]
    metrics = CognitiveMetrics(
        focus=_jitter(base_metrics.focus, 0),
        meditation=_jitter(base_metrics.meditation, 2),
        attention=_jitter(base_metrics.attention, 4),
    )
    waves = WaveBands(
        alpha=_jitter(base_waves.alpha, 1),
        beta=_jitter(base_waves.beta, 3),
        theta=_jitter(base_waves.theta, 5),
    )

    return TelemetryFrame(
        timestamp=time.time(),
        preset=preset,
        metrics=metrics,
        waves=waves,
        intent=parse_intent(metrics, waves),
    )
