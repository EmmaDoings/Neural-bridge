"""Discrete intent state machine.

Continuous EEG should not fire a UI action on every frame. This module turns
a stream of metrics into rare, deliberate intents using four guards:

* **threshold** - the metric must exceed an enter value,
* **sustain**   - it must stay there for ``sustain_seconds``,
* **hysteresis**- re-arming requires dropping below ``release_threshold``,
* **cooldown**  - a hard minimum gap between actions.

A second channel triggers on jaw-clench EMG: the band-passed RMS must exceed
an adaptive baseline by ``emg_ratio_threshold`` for ``emg_frames`` in a row.

Labels/actions mirror ``backend/app/simulator.py`` so the 3-D hologram reacts
identically to simulated and real telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass

from .metrics import Metrics

# Same palette as the backend simulator, plus a distinct motor colour.
COLORS = {
    "precision_execution": "#38bdf8",
    "calm_space": "#a78bfa",
    "creative_synthesis": "#f59e0b",
    "spatial_navigation": "#22c55e",
    "ambient_monitoring": "#94a3b8",
    "motor_select": "#f97316",
}

DEFAULT_COLOR = COLORS["ambient_monitoring"]


def classify(metrics: Metrics) -> tuple[str, float, str]:
    """Map a metric snapshot onto (label, confidence, action)."""

    if metrics.focus > 0.86 and metrics.attention > 0.86:
        return "precision_execution", 0.93, "stabilise"
    if metrics.meditation > 0.82 and metrics.focus < 0.55:
        return "calm_space", 0.88, "breathe"
    if metrics.meditation > 0.6 and metrics.attention > 0.6:
        return "creative_synthesis", 0.79, "compose"
    if metrics.attention > 0.78:
        return "spatial_navigation", 0.84, "navigate"
    return "ambient_monitoring", 0.62, "observe"


@dataclass(frozen=True)
class IntentState:
    label: str
    confidence: float
    action: str
    color: str
    triggered: bool


class IntentEngine:
    """Stateful, time-driven intent detector (clock injected for tests)."""

    def __init__(
        self,
        *,
        enter_threshold: float = 0.85,
        release_threshold: float = 0.75,
        sustain_seconds: float = 1.5,
        cooldown_seconds: float = 4.0,
        emg_ratio_threshold: float = 2.5,
        emg_frames: int = 2,
        emg_cooldown_seconds: float = 0.5,
        baseline_alpha: float = 0.02,
    ) -> None:
        if release_threshold >= enter_threshold:
            raise ValueError("release_threshold must be below enter_threshold")
        if sustain_seconds < 0 or cooldown_seconds < 0:
            raise ValueError("durations must be non-negative")
        if emg_frames < 1:
            raise ValueError("emg_frames must be >= 1")

        self.enter_threshold = enter_threshold
        self.release_threshold = release_threshold
        self.sustain_seconds = sustain_seconds
        self.cooldown_seconds = cooldown_seconds
        self.emg_ratio_threshold = emg_ratio_threshold
        self.emg_frames = emg_frames
        self.emg_cooldown_seconds = emg_cooldown_seconds
        self.baseline_alpha = baseline_alpha

        self._armed = True
        self._focus_since: float | None = None
        self._last_focus_action: float | None = None
        self._last_emg_action: float | None = None
        self._emg_baseline: float | None = None
        self._emg_streak = 0

    # -- public API --------------------------------------------------------
    def update(self, metrics: Metrics, now: float) -> IntentState:
        # ---- EMG ----------------------------------------------------------
        if self._emg_baseline is None:
            self._emg_baseline = metrics.emg
        baseline = max(self._emg_baseline, 1e-9)
        emg_ratio = metrics.emg / baseline
        clenching = emg_ratio >= self.emg_ratio_threshold

        self._emg_streak = self._emg_streak + 1 if clenching else 0
        emg_cooldown_ok = (
            self._last_emg_action is None
            or now - self._last_emg_action >= self.emg_cooldown_seconds
        )

        fired: str | None = None
        if self._emg_streak >= self.emg_frames and emg_cooldown_ok:
            fired = "emg"
            self._last_emg_action = now
            self._emg_streak = 0

        # ---- sustained focus ---------------------------------------------
        if metrics.focus >= self.enter_threshold:
            if self._focus_since is None:
                self._focus_since = now
            cooldown_ok = (
                self._last_focus_action is None
                or now - self._last_focus_action >= self.cooldown_seconds
            )
            if (
                fired is None
                and self._armed
                and cooldown_ok
                and now - self._focus_since >= self.sustain_seconds
            ):
                fired = "focus"
                self._last_focus_action = now
                self._armed = False
                self._focus_since = None
        else:
            self._focus_since = None
            if metrics.focus <= self.release_threshold:
                self._armed = True

        # Adapt the baseline only while the jaw is quiet, and after the
        # decision, so a clench can never mask its own trigger.
        if not clenching:
            alpha = self.baseline_alpha
            self._emg_baseline = alpha * metrics.emg + (1.0 - alpha) * self._emg_baseline  # type: ignore[operator]

        # ---- output ------------------------------------------------------
        label, confidence, action = classify(metrics)
        if fired == "emg":
            label = "motor_select"
            confidence = max(confidence, min(0.99, 0.6 + emg_ratio / (2.0 * self.emg_ratio_threshold)))
            action = "select"
        elif fired == "focus":
            label = "precision_execution"
            confidence = max(confidence, 0.9)
            action = "select"

        return IntentState(
            label=label,
            confidence=max(0.0, min(1.0, confidence)),
            action=action,
            color=COLORS.get(label, DEFAULT_COLOR),
            triggered=fired is not None,
        )

    @property
    def emg_baseline(self) -> float | None:
        return self._emg_baseline
