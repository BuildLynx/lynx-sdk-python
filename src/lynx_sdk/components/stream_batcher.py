"""
Stream batcher: discrete sampling-independent operations for a Channel Stream.
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
import logging
import threading
import time

# -Lynx Imports-
from lynx_sdk.utils.json_tools import trim_payload_by_contents, PayloadBuildingError

# -External Imports-



# === CONSTANTS ===

DEFAULT_SAMPLE_INTERVAL = 1.0
DEFAULT_NUM_SAMPLES = 0
DEFAULT_MAX_INTERVAL = 300.0
DEFAULT_MAX_SAMPLES = 1

NS_PER_S = 1_000_000_000


# === GLOBALS VARIABLES ===



# === FUNCTIONS ===

def resolve_batch_limits(payload: Dict[str, Any]) -> tuple[float, int]:
    """
    Read batch.maxInterval / batch.maxSamples from a Stream payload, applying defaults
    for an omitted batch object or omitted fields. 0 disables that limit.
    """
    batch = payload.get("batch")
    if not isinstance(batch, dict):
        batch = {}
    max_interval = batch.get("maxInterval", DEFAULT_MAX_INTERVAL)
    max_samples = batch.get("maxSamples", DEFAULT_MAX_SAMPLES)
    return float(max_interval), int(max_samples)


def _is_full_contents(contents: Any) -> bool:
    return contents is True or contents == {}


def _is_discarded_sample(data: Any) -> bool:
    return data is None or data == {}


# === CLASSES ===

class StreamBatcher:
    """
    Open-batch + timer for one Stream. Operations are serialized on a lock.

    Sampling (add_sample) and flushing (on_max_interval / end_stream) are independent:
    the timer fires even if the sample function is blocked. Publish is a callback so a
    later event loop can own I/O without changing these rules.
    """

    def __init__(
        self,
        contents: Dict[str, Any] | bool,
        max_interval: float,
        max_samples: int,
        num_samples: int,
        publish: Callable[[List[Dict[str, Any]]], None],
        logger: Optional[logging.Logger] = None,
        on_ended: Optional[Callable[[], None]] = None):
        """
        Args:
            contents: Stream contents filter. True or {} means include all.
            max_interval: Seconds an open batch may wait. 0 = no time limit.
            max_samples: Max samples per published message. 0 = no count limit.
            num_samples: Stream-lifetime cap on admitted samples. 0 = infinite.
            publish: Called with the JSON array to send on `<` (may be empty).
            logger: Optional logger for contents-filter errors.
            on_ended: Called once when the stream transitions to ended (outside the lock).
        """
        self._contents = contents
        self._max_interval = float(max_interval)
        self._max_samples = int(max_samples)
        self._num_samples = int(num_samples)
        self._publish = publish
        self._logger = logger
        self._on_ended = on_ended

        self._lock = threading.Lock()
        self._buffer: List[Dict[str, Any]] = []
        self._last_data: Any = None
        self._admitted = 0
        self._ended = True
        self._stream_start_ns = 0
        self._timer: Optional[threading.Timer] = None
        self._timer_gen = 0

    def start(self) -> None:
        """Open an empty batch and start the batch timer (start_stream)."""
        with self._lock:
            self._buffer = []
            self._last_data = None
            self._admitted = 0
            self._ended = False
            self._stream_start_ns = time.perf_counter_ns()
            self._arm_timer_locked()

    def add_sample(self, data: Any) -> bool:
        """
        Offer one generator yield to the open batch.

        Returns:
            True if the stream is still active, False if it has ended (or already had).
        """
        on_ended: Optional[Callable[[], None]] = None
        with self._lock:
            if self._ended:
                return False

            if not _is_full_contents(self._contents):
                try:
                    data = trim_payload_by_contents(data, self._contents, self._last_data)
                except PayloadBuildingError as e:
                    if self._logger is not None:
                        self._logger.error(f"Error trimming payload: {e.message}")
                    return True
                if _is_discarded_sample(data):
                    return True

            elapsed = time.perf_counter_ns() - self._stream_start_ns
            self._buffer.append({
                "s": elapsed // NS_PER_S,
                "ns": elapsed % NS_PER_S,
                "data": data
            })
            self._last_data = data
            self._admitted += 1

            if self._max_samples > 0 and len(self._buffer) >= self._max_samples:
                self._flush_locked(ending=False)

            if self._num_samples > 0 and self._admitted >= self._num_samples:
                self._ended = True
                self._flush_locked(ending=True)
                on_ended = self._on_ended

        if on_ended is not None:
            on_ended()
        return on_ended is None

    def on_max_interval(self) -> None:
        """Time-based flush, including [] if the buffer is empty. No-op if ended or stale timer."""
        with self._lock:
            if self._ended:
                return
            self._flush_locked(ending=False)

    def end_stream(self) -> None:
        """Flush once (including [] if empty) and mark the stream ended. Idempotent."""
        on_ended: Optional[Callable[[], None]] = None
        with self._lock:
            if self._ended:
                return
            self._ended = True
            self._flush_locked(ending=True)
            on_ended = self._on_ended
        if on_ended is not None:
            on_ended()

    def _on_timer(self, gen: int) -> None:
        with self._lock:
            if self._ended or gen != self._timer_gen:
                return
            self._flush_locked(ending=False)

    def _flush_locked(self, ending: bool) -> None:
        payload = self._buffer
        self._buffer = []
        self._cancel_timer_locked()
        self._publish(payload)
        if not ending:
            self._arm_timer_locked()

    def _cancel_timer_locked(self) -> None:
        self._timer_gen += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _arm_timer_locked(self) -> None:
        self._cancel_timer_locked()
        if self._ended or self._max_interval <= 0:
            return
        gen = self._timer_gen
        timer = threading.Timer(self._max_interval, self._on_timer, args=(gen,))
        timer.daemon = True
        self._timer = timer
        timer.start()
