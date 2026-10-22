"""Entry point: ``python -m nb_bridge``.

Examples (run from the ``hardware/`` directory):

    .venv\\Scripts\\python -m nb_bridge --check          # validate config + board
    .venv\\Scripts\\python -m nb_bridge                  # synthetic board, deployed API
    $env:NB_BOARD="cyton"; $env:NB_SERIAL_PORT="COM3"; .venv\\Scripts\\python -m nb_bridge
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import os
import sys
import time
import urllib.request

import numpy as np

from .boards import BoardSession, BoardUnavailable, build_region_map
from .client import DeviceClient
from .config import BridgeConfig, ConfigError, VALID_BOARDS, VALID_PRESETS
from .intent import IntentEngine, IntentState
from .metrics import Metrics, MetricsEngine, ratios_from_bands
from .protocol import build_telemetry_frame
from .signal import MIN_SAMPLES, emg_rms, relative_band_powers

logger = logging.getLogger("nb_bridge")


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


class Producer:
    """Turns board windows into telemetry frames.

    Kept as a class so the board, engines and mutable preset live for the
    whole session and can be driven by backend commands.
    """

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.info, self.regions = build_region_map(config.board)
        self.session = BoardSession(config.board, config.serial_port)
        self.engine = MetricsEngine(
            ema_alpha=config.ema_alpha,
            calibration_seconds=config.calibration_seconds,
            sample_hz=config.update_hz,
        )
        self.intent = IntentEngine(
            enter_threshold=config.intent_focus_enter,
            release_threshold=config.intent_focus_release,
            sustain_seconds=config.intent_sustain_seconds,
            cooldown_seconds=config.intent_cooldown_seconds,
            emg_ratio_threshold=config.emg_ratio_threshold,
            emg_frames=config.emg_frames,
        )
        self.preset = config.preset
        self._logged_calibration_start = False
        self._logged_calibration_done = False

    def start(self) -> None:
        self.session.open()
        logger.info(
            "board=%s sr=%dHz eeg=%dch regions frontal=%s central=%s lateral=%s occipital=%s",
            self.info.key,
            self.info.sampling_rate,
            len(self.info.eeg_channels),
            list(self.regions.frontal),
            list(self.regions.central),
            list(self.regions.lateral),
            list(self.regions.occipital),
        )
        if self.config.calibration_seconds > 0:
            logger.info(
                "calibrating: keep still for %.0fs (eyes open, then close them halfway)",
                self.config.calibration_seconds,
            )
            self._logged_calibration_start = True

    def close(self) -> None:
        self.session.close()

    # -- commands from the backend / dashboard -----------------------------
    def on_command(self, action: str, payload: dict) -> None:
        if action in ("set_preset", "preset"):
            preset = payload.get("preset") or payload.get("name")
            if preset not in VALID_PRESETS:
                logger.warning("ignoring unknown preset %r", preset)
                return
            self.preset = preset
            logger.info("preset -> %s", preset)
        elif action == "calibrate":
            seconds = payload.get("seconds", self.config.calibration_seconds)
            try:
                seconds = float(seconds)
            except (TypeError, ValueError):
                seconds = self.config.calibration_seconds
            self.engine = MetricsEngine(
                ema_alpha=self.config.ema_alpha,
                calibration_seconds=max(0.0, seconds),
                sample_hz=self.config.update_hz,
            )
            self._logged_calibration_start = False
            self._logged_calibration_done = False
            logger.info("restarting calibration for %.0fs", seconds)
        elif action == "ping":
            logger.debug("ping from backend")
        else:
            logger.info("unhandled command %r", action)

    # -- frame generation --------------------------------------------------
    def produce(self) -> dict | None:
        data = self.session.read(self.config.window_seconds)
        if data.ndim != 2 or data.shape[1] < MIN_SAMPLES:
            return None

        central_bands = relative_band_powers(
            data, self.regions.central, self.info.sampling_rate
        )
        if central_bands is None:
            return None
        occipital_bands = relative_band_powers(
            data, self.regions.occipital, self.info.sampling_rate
        )
        if occipital_bands is None:
            occipital_bands = central_bands

        emg = max(
            (
                emg_rms(data, channel, self.info.sampling_rate, self.config.emg_band)
                for channel in self.regions.lateral
            ),
            default=0.0,
        )

        reading = ratios_from_bands(central_bands, occipital_bands, emg)
        metrics: Metrics = self.engine.update(reading)
        state: IntentState = self.intent.update(metrics, time.monotonic())

        if self.engine.calibration_active and not self._logged_calibration_done:
            self._logged_calibration_done = True
            logger.info("calibration complete; metrics are now personalised")

        return build_telemetry_frame(
            preset=self.preset,
            metrics=metrics,
            intent=state,
            source=None,
        )


def _check_backend(api_base: str, timeout: float) -> bool:
    url = f"{api_base}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.error("backend check failed for %s: %s", url, exc)
        return False
    logger.info("backend healthy: %s -> %s", url, body.strip())
    return True


def run_check(config: BridgeConfig, skip_board: bool) -> int:
    ok = True
    logger.info(
        "config: api=%s board=%s port=%s preset=%s update=%.1fHz window=%.1fs",
        config.api_base,
        config.board,
        config.serial_port or "-",
        config.preset,
        config.update_hz,
        config.window_seconds,
    )
    if not _check_backend(config.api_base, config.request_timeout):
        ok = False
    if skip_board:
        return 0 if ok else 1

    producer = Producer(config)
    try:
        producer.start()
    except BoardUnavailable as exc:
        logger.error("%s", exc)
        return 1
    try:
        deadline = time.monotonic() + 3.0
        frame = None
        while time.monotonic() < deadline and frame is None:
            time.sleep(0.25)
            frame = producer.produce()
        if frame is None:
            logger.error("board produced no usable frame within 3s")
            return 1
        logger.info("sample frame: %s", frame)
    finally:
        producer.close()
    return 0 if ok else 1


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Neural Bridge hardware bridge")
    parser.add_argument("--api-base", help="override NB_API_BASE")
    parser.add_argument("--board", choices=VALID_BOARDS, help="override NB_BOARD")
    parser.add_argument("--serial-port", help="override NB_SERIAL_PORT")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate config, ping the backend and print one live frame",
    )
    parser.add_argument(
        "--no-board",
        action="store_true",
        help="with --check, skip opening the board",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="stop after N seconds (0 = run until Ctrl+C)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = BridgeConfig.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    overrides: dict = {}
    if args.api_base:
        overrides["api_base"] = args.api_base.rstrip("/")
    if args.board:
        overrides["board"] = args.board
    if args.serial_port:
        overrides["serial_port"] = args.serial_port
    if overrides:
        config = dataclasses.replace(config, **overrides)

    configure_logging(config.log_level)
    if config.board != "synthetic" and not config.serial_port:
        logger.error("NB_SERIAL_PORT is required for board %s", config.board)
        return 2

    if args.check:
        return run_check(config, skip_board=args.no_board)

    producer = Producer(config)
    try:
        producer.start()
    except BoardUnavailable as exc:
        logger.error("%s", exc)
        return 1

    client = DeviceClient(
        config,
        on_command=producer.on_command,
        fatal_exceptions=(BoardUnavailable,),
    )

    async def runner() -> None:
        task = asyncio.create_task(client.run(producer.produce))
        if args.duration > 0:
            await asyncio.wait_for(asyncio.shield(task), timeout=args.duration)
        else:
            await task

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        logger.info("stopping on Ctrl+C")
    except asyncio.TimeoutError:
        logger.info("duration reached; stopping")
    except Exception as exc:
        logger.error("fatal: %s: %s", type(exc).__name__, exc)
        return 1
    finally:
        client.stop()
        producer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
