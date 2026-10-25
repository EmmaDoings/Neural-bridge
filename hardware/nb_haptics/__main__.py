"""Entry point: ``python -m nb_haptics``.

Run from the ``hardware/`` directory:

    .venv\\Scripts\\python -m nb_haptics --check --pulse   # mock actuator
    .venv\\Scripts\\python -m nb_haptics                   # wait for pulses

Serial actuator (Arduino/ESP32, see ``haptics_firmware/``):

    $env:NB_HAPTICS_DRIVER="serial"
    $env:NB_HAPTICS_SERIAL_PORT="COM4"
    .venv\\Scripts\\python -m nb_haptics
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import sys
import urllib.request

from nb_common.client import DeviceClient
from nb_common.config import ConfigError, validate_http_url

from .config import HapticsConfig, VALID_DRIVERS
from .controller import HapticsController
from .drivers import HapticsUnavailable, build_driver

logger = logging.getLogger("nb_haptics")


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def check_backend(api_base: str, timeout: float) -> bool:
    url = f"{api_base}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.error("backend check failed for %s: %s", url, exc)
        return False
    logger.info("backend healthy: %s -> %s", url, body.strip())
    return True


def run_check(config: HapticsConfig, pulse: bool) -> int:
    ok = check_backend(config.api_base, config.request_timeout)
    logger.info(
        "config: api=%s device=%s driver=%s port=%s baud=%d",
        config.api_base,
        config.device_name,
        config.driver,
        config.serial_port or "-",
        config.baud_rate,
    )
    try:
        driver = build_driver(config)
    except HapticsUnavailable as exc:
        logger.error("%s", exc)
        return 1
    try:
        logger.info("actuator: %s", driver.describe())
        if pulse:
            logger.info("sending test pulse (0.60, 250 ms)")
            try:
                driver.pulse(0.60, 250)
            except (HapticsUnavailable, ValueError) as exc:
                logger.error("test pulse failed: %s", exc)
                ok = False
    finally:
        driver.close()
    return 0 if ok else 1


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Neural Bridge haptics bridge")
    parser.add_argument("--api-base", help="override NB_HAPTICS_API_BASE")
    parser.add_argument(
        "--driver", choices=VALID_DRIVERS, help="override NB_HAPTICS_DRIVER"
    )
    parser.add_argument(
        "--serial-port", help="override NB_HAPTICS_SERIAL_PORT (for example COM4)"
    )
    parser.add_argument(
        "--baud", type=int, help="override NB_HAPTICS_BAUD (default 115200)"
    )
    parser.add_argument(
        "--device-name", help="override the name shown in GET /devices"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate config, ping the backend, and open the actuator",
    )
    parser.add_argument(
        "--pulse",
        action="store_true",
        help="with --check, send one test pulse (may move a connected motor)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="stop after N seconds (0 = run until Ctrl+C)",
    )
    args = parser.parse_args(argv)
    if args.pulse and not args.check:
        parser.error("--pulse requires --check")
    if args.duration < 0:
        parser.error("--duration must be >= 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = HapticsConfig.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    overrides: dict = {}
    if args.api_base:
        try:
            overrides["api_base"] = validate_http_url("--api-base", args.api_base)
        except ConfigError as exc:
            print(f"configuration error: {exc}", file=sys.stderr)
            return 2
    if args.driver:
        overrides["driver"] = args.driver
    if args.serial_port:
        overrides["serial_port"] = args.serial_port
    if args.baud is not None:
        if args.baud < 1200:
            print("configuration error: --baud must be >= 1200", file=sys.stderr)
            return 2
        overrides["baud_rate"] = args.baud
    if args.device_name:
        overrides["device_name"] = args.device_name
    if overrides:
        config = dataclasses.replace(config, **overrides)

    configure_logging(config.log_level)
    if args.check:
        return run_check(config, pulse=args.pulse)

    try:
        driver = build_driver(config)
    except HapticsUnavailable as exc:
        logger.error("%s", exc)
        return 1

    controller = HapticsController(driver)
    client = DeviceClient(config, on_command=controller.on_command)
    logger.info(
        "starting haptics bridge: api=%s device=%s actuator=%s",
        config.api_base,
        config.device_name,
        driver.describe(),
    )

    async def runner() -> None:
        task = asyncio.create_task(client.run())
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
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
