"""
Active Stream: admission, open batch, and stream lifetime for one Channel Stream.

Generative AI was used in the Creation/Modification of this file.

ActiveStream owns the lock required by A2.1 section 7.6 (add_sample and
on_max_interval must not interleave). AdmissionGate and OpenBatch are
unsynchronized helpers called only under that lock.

A scheduler -- the Service main loop, a pumped user loop, or asyncio -- calls
flush_if_due() when the deadline has passed. add_sample applies the admission
rules of A2.1 section 7.6: rate gate, then contents filtering.
"""

from typing import Any, Callable, Dict, List, NamedTuple, Optional
import logging
import threading
import time

from lynx_sdk.protocol.contents import trim_payload_by_contents, PayloadBuildingError
from lynx_sdk.protocol.time_units import NS_PER_S


DEFAULT_SAMPLE_INTERVAL = 1.0
DEFAULT_TOTAL_SAMPLE_LIMIT = 0
DEFAULT_MAX_INTERVAL = 300.0
DEFAULT_BATCH_SIZE_LIMIT = 1


class BatchLimits(NamedTuple):
    max_interval: float
    batch_size_limit: int


def resolve_batch_limits(payload: Dict[str, Any]) -> BatchLimits:
    """
    Read batch.maxInterval / batch.maxSamples from a Stream payload, applying defaults
    for an omitted batch object or omitted fields. 0 disables that limit.
    """
    batch = payload.get("batch")
    if not isinstance(batch, dict):
        batch = {}
    max_interval = batch.get("maxInterval", DEFAULT_MAX_INTERVAL)
    batch_size_limit = batch.get("maxSamples", DEFAULT_BATCH_SIZE_LIMIT)
    return BatchLimits(float(max_interval), int(batch_size_limit))


def _is_discarded_sample(data: Any) -> bool:
    return data is None or data == {}


class AdmissionGate:
    """
    Rate gate and contents filter for one Stream. No lock; the caller serializes.
    """

    def __init__(
        self,
        contents: Dict[str, Any] | bool,
        sample_interval: Optional[float] = None,
        logger: Optional[logging.Logger] = None):
        self._contents = contents
        self._logger = logger
        if sample_interval is None:
            self._sample_interval_ns: Optional[int] = None
        else:
            self._sample_interval_ns = int(float(sample_interval) * NS_PER_S)
        self._contents_baseline: Any = None
        self._last_admitted_ns: Optional[int] = None

    def reset(self) -> None:
        self._contents_baseline = None
        self._last_admitted_ns = None

    def admit(self, data: Any, now_ns: int) -> Optional[Any]:
        """
        Apply admission rules in order: rate gate, then contents filtering.

        Returns the (possibly trimmed) data if admitted, or None if discarded.
        """
        if not self._passes_rate_gate(now_ns):
            return None

        if self._contents is not True:
            try:
                data = trim_payload_by_contents(data, self._contents, self._contents_baseline)
            except PayloadBuildingError as e:
                if self._logger is not None:
                    self._logger.error(f"Error trimming payload: {e.message}")
                return None
            if _is_discarded_sample(data):
                return None

        self._contents_baseline = data
        self._last_admitted_ns = now_ns
        return data

    def _passes_rate_gate(self, now_ns: int) -> bool:
        if self._sample_interval_ns is None or self._sample_interval_ns <= 0:
            return True
        if self._last_admitted_ns is None:
            return True
        return (now_ns - self._last_admitted_ns) >= self._sample_interval_ns


class OpenBatch:
    """
    Buffer, batch timer, and flush for one Stream. No lock; the caller serializes.
    """

    def __init__(
        self,
        max_interval: float,
        batch_size_limit: int,
        publish: Callable[[List[Dict[str, Any]]], None]):
        self._max_interval = float(max_interval)
        self._batch_size_limit = int(batch_size_limit)
        self._publish = publish
        self._buffer: List[Dict[str, Any]] = []
        self._flush_deadline_ns: Optional[int] = None

    def reset(self) -> None:
        self._buffer = []
        self._flush_deadline_ns = None

    def append(self, sample: Dict[str, Any]) -> None:
        self._buffer.append(sample)

    def is_full(self) -> bool:
        return self._batch_size_limit > 0 and len(self._buffer) >= self._batch_size_limit

    def deadline_ns(self) -> Optional[int]:
        return self._flush_deadline_ns

    def arm_deadline(self, stream_open: bool) -> None:
        if not stream_open or self._max_interval <= 0:
            self._flush_deadline_ns = None
            return
        self._flush_deadline_ns = time.perf_counter_ns() + int(self._max_interval * NS_PER_S)

    def flush_and_rearm(self, stream_open: bool) -> None:
        self._publish_and_clear()
        self.arm_deadline(stream_open)

    def flush_final(self) -> None:
        self._publish_and_clear()

    def _publish_and_clear(self) -> None:
        payload = self._buffer
        self._buffer = []
        self._flush_deadline_ns = None
        self._publish(payload)


class ActiveStream:
    """
    One active Stream: lifetime, admission, and the open batch.

    Sampling (add_sample) and flushing (flush_if_due / end_stream) are independent:
    flush_if_due() flushes even if the data source is blocked. Publish is a callback
    so the runtime owns I/O. Operations are serialized on a lock.
    """

    def __init__(
        self,
        contents: Dict[str, Any] | bool,
        max_interval: float,
        batch_size_limit: int,
        total_sample_limit: int,
        publish: Callable[[List[Dict[str, Any]]], None],
        logger: Optional[logging.Logger] = None,
        on_ended: Optional[Callable[[], None]] = None,
        sample_interval: Optional[float] = None):
        """
        Args:
            contents: Stream contents filter. True means include all.
            max_interval: Seconds an open batch may wait. 0 = no time limit.
            batch_size_limit: Max samples per published message. 0 = no count limit.
            total_sample_limit: Stream-lifetime cap on admitted samples. 0 = infinite.
            publish: Called with the JSON array to send on `<` (may be empty).
            logger: Optional logger for contents-filter errors.
            on_ended: Called once when the stream transitions to ended (outside the lock).
            sample_interval: Minimum seconds between admitted samples. None disables
                the rate gate (the Channel did not advertise sampleInterval). 0 admits
                every offered sample.
        """
        self._total_sample_limit = int(total_sample_limit)
        self._on_ended = on_ended
        self._gate = AdmissionGate(
            contents=contents,
            sample_interval=sample_interval,
            logger=logger)
        self._batch = OpenBatch(
            max_interval=max_interval,
            batch_size_limit=batch_size_limit,
            publish=publish)

        self._lock = threading.Lock()
        self._admitted = 0
        self._open = False
        self._stream_start_ns = 0

    def flush_deadline_ns(self) -> Optional[int]:
        """perf_counter_ns instant at which flush_if_due() should flush, or None."""
        with self._lock:
            return self._batch.deadline_ns()

    def start_stream(self) -> None:
        """Open an empty batch and arm the flush deadline."""
        with self._lock:
            self._gate.reset()
            self._batch.reset()
            self._admitted = 0
            self._open = True
            self._stream_start_ns = time.perf_counter_ns()
            self._batch.arm_deadline(True)

    def add_sample(self, data: Any) -> bool:
        """
        Offer one sample to the open batch.

        Applies admission rules in order: rate gate, then contents filtering.
        Discarded samples have no observable effect.

        Returns:
            True if the stream is still open, False if it has ended (or already had).
            Unrelated to whether this sample was admitted.
        """
        on_ended: Optional[Callable[[], None]] = None
        with self._lock:
            if not self._open:
                return False

            now_ns = time.perf_counter_ns()
            admitted = self._gate.admit(data, now_ns)
            if admitted is None:
                return True

            elapsed = now_ns - self._stream_start_ns
            self._batch.append({
                "s": elapsed // NS_PER_S,
                "ns": elapsed % NS_PER_S,
                "data": admitted
            })
            self._admitted += 1

            if self._batch.is_full():
                self._batch.flush_and_rearm(stream_open=True)

            if self._total_sample_limit > 0 and self._admitted >= self._total_sample_limit:
                self._open = False
                self._batch.flush_final()
                on_ended = self._on_ended

        if on_ended is not None:
            on_ended()
        return on_ended is None

    def flush_if_due(self, now_ns: Optional[int] = None) -> None:
        """
        Flush if the deadline has passed, including [] if the buffer is empty.
        No-op if ended or if time-based flush is disabled.
        """
        if now_ns is None:
            now_ns = time.perf_counter_ns()
        with self._lock:
            deadline = self._batch.deadline_ns()
            if not self._open or deadline is None:
                return
            if now_ns >= deadline:
                self._batch.flush_and_rearm(stream_open=True)

    def end_stream(self) -> None:
        """Flush once (including [] if empty) and mark the stream ended. Idempotent."""
        on_ended: Optional[Callable[[], None]] = None
        with self._lock:
            if not self._open:
                return
            self._open = False
            self._batch.flush_final()
            on_ended = self._on_ended
        if on_ended is not None:
            on_ended()
