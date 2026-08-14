"""
Stream batcher: discrete sampling-independent operations for a Channel Stream.

Generative AI was used in the Creation/Modification of this file.

The batcher owns an open buffer and a *deadline*, not a thread. A scheduler --
the Service main loop, a pumped user loop, or asyncio -- calls service() when
the deadline has passed. add_sample applies the admission rules of A2.1
section 7.6: rate gate, then contents filtering.
"""

from typing import Any, Callable, Dict, List, Optional
import logging
import threading
import time

from lynx_sdk.protocol.contents import trim_payload_by_contents, PayloadBuildingError


DEFAULT_SAMPLE_INTERVAL = 1.0
DEFAULT_NUM_SAMPLES = 0
DEFAULT_MAX_INTERVAL = 300.0
DEFAULT_MAX_SAMPLES = 1

NS_PER_S = 1_000_000_000


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


def _is_discarded_sample(data: Any) -> bool:
    return data is None or data == {}


class StreamBatcher:
    """
    Open-batch + flush deadline for one Stream. Operations are serialized on a lock.

    Sampling (add_sample) and flushing (service / end_stream) are independent:
    service() flushes even if the data source is blocked. Publish is a callback so
    the runtime owns I/O.
    """

    def __init__(
        self,
        contents: Dict[str, Any] | bool,
        max_interval: float,
        max_samples: int,
        num_samples: int,
        publish: Callable[[List[Dict[str, Any]]], None],
        logger: Optional[logging.Logger] = None,
        on_ended: Optional[Callable[[], None]] = None,
        sample_interval: Optional[float] = None):
        """
        Args:
            contents: Stream contents filter. True means include all.
            max_interval: Seconds an open batch may wait. 0 = no time limit.
            max_samples: Max samples per published message. 0 = no count limit.
            num_samples: Stream-lifetime cap on admitted samples. 0 = infinite.
            publish: Called with the JSON array to send on `<` (may be empty).
            logger: Optional logger for contents-filter errors.
            on_ended: Called once when the stream transitions to ended (outside the lock).
            sample_interval: Minimum seconds between admitted samples. None disables
                the rate gate (the Channel did not advertise sampleInterval). 0 admits
                every offered sample.
        """
        self._contents = contents
        self._max_interval = float(max_interval)
        self._max_samples = int(max_samples)
        self._num_samples = int(num_samples)
        self._publish = publish
        self._logger = logger
        self._on_ended = on_ended
        if sample_interval is None:
            self._sample_interval_ns: Optional[int] = None
        else:
            self._sample_interval_ns = int(float(sample_interval) * NS_PER_S)

        self._lock = threading.Lock()
        self._buffer: List[Dict[str, Any]] = []
        self._last_data: Any = None
        self._admitted = 0
        self._ended = True
        self._stream_start_ns = 0
        self._last_admitted_ns: Optional[int] = None
        self._flush_deadline_ns: Optional[int] = None

    def flush_deadline_ns(self) -> Optional[int]:
        """perf_counter_ns instant at which service() should flush, or None."""
        with self._lock:
            return self._flush_deadline_ns

    def start(self) -> None:
        """Open an empty batch and arm the flush deadline (start_stream)."""
        with self._lock:
            self._buffer = []
            self._last_data = None
            self._admitted = 0
            self._ended = False
            self._stream_start_ns = time.perf_counter_ns()
            self._last_admitted_ns = None
            self._arm_deadline_locked()

    def add_sample(self, data: Any) -> bool:
        """
        Offer one sample to the open batch.

        Applies admission rules in order: rate gate, then contents filtering.
        Discarded samples have no observable effect.

        Returns:
            True if the stream is still active, False if it has ended (or already had).
        """
        on_ended: Optional[Callable[[], None]] = None
        with self._lock:
            if self._ended:
                return False

            now_ns = time.perf_counter_ns()
            if not self._passes_rate_gate_locked(now_ns):
                return True

            if self._contents is not True:
                try:
                    data = trim_payload_by_contents(data, self._contents, self._last_data)
                except PayloadBuildingError as e:
                    if self._logger is not None:
                        self._logger.error(f"Error trimming payload: {e.message}")
                    return True
                if _is_discarded_sample(data):
                    return True

            elapsed = now_ns - self._stream_start_ns
            self._buffer.append({
                "s": elapsed // NS_PER_S,
                "ns": elapsed % NS_PER_S,
                "data": data
            })
            self._last_data = data
            self._last_admitted_ns = now_ns
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

    def service(self, now_ns: Optional[int] = None) -> None:
        """
        Flush if the deadline has passed, including [] if the buffer is empty.
        No-op if ended or if time-based flush is disabled.
        """
        if now_ns is None:
            now_ns = time.perf_counter_ns()
        with self._lock:
            if self._ended or self._flush_deadline_ns is None:
                return
            if now_ns >= self._flush_deadline_ns:
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

    def _passes_rate_gate_locked(self, now_ns: int) -> bool:
        if self._sample_interval_ns is None or self._sample_interval_ns <= 0:
            return True
        if self._last_admitted_ns is None:
            return True
        return (now_ns - self._last_admitted_ns) >= self._sample_interval_ns

    def _flush_locked(self, ending: bool) -> None:
        payload = self._buffer
        self._buffer = []
        self._flush_deadline_ns = None
        self._publish(payload)
        if not ending:
            self._arm_deadline_locked()

    def _arm_deadline_locked(self) -> None:
        if self._ended or self._max_interval <= 0:
            self._flush_deadline_ns = None
            return
        self._flush_deadline_ns = time.perf_counter_ns() + int(self._max_interval * NS_PER_S)
