"""Collect and validate a real Cyton telemetry sample after the GUI impedance check.

Run from ``hardware/`` with ``NB_BOARD=cyton`` and ``NB_SERIAL_PORT`` set.
The script never sends data to the backend, so it is safe to use while tuning
electrodes. It exits non-zero when the board does not produce enough valid
frames for the selected duration.
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from nb_bridge.__main__ import Producer, configure_logging
from nb_bridge.boards import BoardUnavailable
from nb_bridge.config import BridgeConfig, ConfigError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a real OpenBCI Cyton stream")
    parser.add_argument("--seconds", type=float, default=30.0, help="capture duration (default: 30)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seconds < 5:
        raise SystemExit("--seconds must be at least 5")
    try:
        config = BridgeConfig.from_env()
    except ConfigError as exc:
        raise SystemExit(f"configuration error: {exc}") from exc
    if config.board not in {"cyton", "cyton_daisy"}:
        raise SystemExit("set NB_BOARD=cyton or NB_BOARD=cyton_daisy before validating")

    configure_logging(config.log_level)
    producer = Producer(config)
    frames: list[dict] = []
    dropped = 0
    try:
        producer.start()
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            frame = producer.produce()
            if frame is None:
                dropped += 1
            else:
                frames.append(frame)
            time.sleep(config.interval_seconds)
    except BoardUnavailable as exc:
        logging.getLogger("nb_bridge.validate").error("%s", exc)
        return 1
    finally:
        producer.close()

    expected = int(args.seconds * config.update_hz * 0.8)
    summary = {
        "board": config.board,
        "seconds": args.seconds,
        "valid_frames": len(frames),
        "dropped_windows": dropped,
        "minimum_expected_frames": expected,
        "triggered_frames": sum(bool(frame["triggered"]) for frame in frames),
    }
    print(json.dumps(summary, indent=2))
    if len(frames) < expected:
        logging.getLogger("nb_bridge.validate").error("insufficient valid frames")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
