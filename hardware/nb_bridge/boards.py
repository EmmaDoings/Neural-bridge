"""Board selection, lifecycle and EEG region mapping.

The empirical details encoded here were verified against brainflow==5.23.0:

* ``BoardShim.get_eeg_channels`` returns *row indices* into the board matrix.
* ``BoardShim.get_eeg_names`` returns the 10-20 names for OpenBCI boards, but
  the synthetic board reports only four names for sixteen channels.
* ``BoardShim.disable_board_logger`` keeps the native JSON banner off stderr.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
from brainflow.board_shim import BrainFlowError

BOARD_IDS = {
    "synthetic": BoardIds.SYNTHETIC_BOARD.value,
    "cyton": BoardIds.CYTON_BOARD.value,
    "cyton_daisy": BoardIds.CYTON_DAISY_BOARD.value,
}

# Electrode -> cognitive region. Names are lower-cased and stripped of
# separators before matching, so "Fp1" and "fp1" behave identically.
REGION_PREFIXES: dict[str, tuple[str, ...]] = {
    "frontal": ("fp", "af", "fz", "f3", "f4", "f7", "f8"),
    "central": ("c3", "c4", "cz", "cp3", "cp4", "cpz"),
    "lateral": ("t7", "t8", "tp7", "tp8", "p7", "p8"),
    "occipital": ("o1", "o2", "oz"),
}


class BoardUnavailable(RuntimeError):
    """The board could not be opened (dongle missing, port busy, ...)."""


@dataclass(frozen=True)
class BoardInfo:
    key: str
    board_id: int
    sampling_rate: int
    eeg_channels: tuple[int, ...]
    eeg_names: tuple[str, ...]
    timestamp_channel: int


@dataclass(frozen=True)
class RegionMap:
    """Row indices used for each metric region.

    Every region is guaranteed non-empty so the metric pipeline always has
    data, even on boards that expose a non-standard montage.
    """

    frontal: tuple[int, ...]
    central: tuple[int, ...]
    lateral: tuple[int, ...]
    occipital: tuple[int, ...]

    def all_channels(self) -> tuple[int, ...]:
        seen: list[int] = []
        for group in (self.frontal, self.central, self.lateral, self.occipital):
            for channel in group:
                if channel not in seen:
                    seen.append(channel)
        return tuple(seen)


def board_info(key: str) -> BoardInfo:
    if key not in BOARD_IDS:
        raise ValueError(f"unknown board {key!r}")
    board_id = BOARD_IDS[key]
    eeg = tuple(int(ch) for ch in BoardShim.get_eeg_channels(board_id))
    names = tuple(str(name) for name in BoardShim.get_eeg_names(board_id))
    return BoardInfo(
        key=key,
        board_id=board_id,
        sampling_rate=int(BoardShim.get_sampling_rate(board_id)),
        eeg_channels=eeg,
        eeg_names=names,
        timestamp_channel=int(BoardShim.get_timestamp_channel(board_id)),
    )


def _normalise(name: str) -> str:
    return "".join(char for char in name.lower() if char.isalnum())


def _match_region(name: str) -> str | None:
    normalised = _normalise(name)
    for region, prefixes in REGION_PREFIXES.items():
        if any(normalised.startswith(prefix) for prefix in prefixes):
            return region
    return None


def _fallback(info: BoardInfo, index: int) -> int:
    """Pick a stable channel when a region is absent from the montage."""

    if not info.eeg_channels:
        raise BoardUnavailable("board reports no EEG channels")
    return info.eeg_channels[min(index, len(info.eeg_channels) - 1)]


def region_map(info: BoardInfo) -> RegionMap:
    """Map 10-20 names onto metric regions.

    The synthetic board has sixteen channels but only four names, so the
    positional fallbacks below give it a usable (if arbitrary) anatomy. Real
    OpenBCI boards always match by name.
    """

    buckets: dict[str, list[int]] = {region: [] for region in REGION_PREFIXES}
    for index, channel in enumerate(info.eeg_channels):
        name = info.eeg_names[index] if index < len(info.eeg_names) else ""
        region = _match_region(name)
        if region is not None:
            buckets[region].append(channel)

    positional = {
        "frontal": 0,
        "central": 1,
        "lateral": 4,
        "occipital": 6,
    }
    resolved: dict[str, tuple[int, ...]] = {}
    for region, default_index in positional.items():
        channels = buckets[region]
        resolved[region] = (
            tuple(channels) if channels else (_fallback(info, default_index),)
        )

    return RegionMap(
        frontal=resolved["frontal"],
        central=resolved["central"],
        lateral=resolved["lateral"],
        occipital=resolved["occipital"],
    )


class BoardSession:
    """Owns the native BrainFlow session and reads rolling windows."""

    def __init__(self, key: str, serial_port: str | None = None) -> None:
        self.info = board_info(key)
        self.serial_port = serial_port
        self._board: BoardShim | None = None
        self._streaming = False

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:
        if self._board is not None:
            return
        BoardShim.disable_board_logger()
        params = BrainFlowInputParams()
        if self.serial_port:
            params.serial_port = self.serial_port
        board = BoardShim(self.info.board_id, params)
        try:
            board.prepare_session()
            board.start_stream(450000)
        except BrainFlowError as exc:
            try:
                board.release_session()
            except BrainFlowError:
                pass
            raise BoardUnavailable(
                f"could not open {self.info.key} board"
                + (f" on {self.serial_port}" if self.serial_port else "")
                + f": {exc}"
            ) from exc
        self._board = board
        self._streaming = True

    def close(self) -> None:
        if self._board is None:
            return
        board = self._board
        self._board = None
        self._streaming = False
        if board.is_prepared():
            try:
                if board.get_board_data_count() >= 0:
                    board.stop_stream()
            except BrainFlowError:
                pass
            try:
                board.release_session()
            except BrainFlowError:
                pass

    # -- data --------------------------------------------------------------
    def read(self, seconds: float) -> np.ndarray:
        """Return the most recent ``seconds`` of battery data.

        The returned matrix has shape ``(rows, samples)`` and may hold fewer
        samples than requested right after startup. Callers must check.
        """

        if self._board is None or not self._streaming:
            raise BoardUnavailable("board session is not open")
        samples = max(1, int(round(self.info.sampling_rate * seconds)))
        try:
            data = self._board.get_current_board_data(samples)
        except BrainFlowError as exc:
            raise BoardUnavailable(f"failed reading board data: {exc}") from exc
        if data is None:
            return np.empty((0, 0), dtype=np.float64)
        return np.asarray(data, dtype=np.float64)

    def __enter__(self) -> "BoardSession":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def build_region_map(key: str) -> tuple[BoardInfo, RegionMap]:
    """Convenience helper used by the entry point and tests."""

    info = board_info(key)
    return info, region_map(info)
