"""
Stream batcher re-export.

Generative AI was used in the Creation/Modification of this file.

The implementation lives in lynx_sdk.protocol.stream_batcher so it stays a
pure protocol state machine. This module keeps the previous import path.
"""

from lynx_sdk.protocol.stream_batcher import (
    DEFAULT_MAX_INTERVAL,
    DEFAULT_MAX_SAMPLES,
    DEFAULT_NUM_SAMPLES,
    DEFAULT_SAMPLE_INTERVAL,
    NS_PER_S,
    StreamBatcher,
    resolve_batch_limits,
)

__all__ = [
    "DEFAULT_MAX_INTERVAL",
    "DEFAULT_MAX_SAMPLES",
    "DEFAULT_NUM_SAMPLES",
    "DEFAULT_SAMPLE_INTERVAL",
    "NS_PER_S",
    "StreamBatcher",
    "resolve_batch_limits",
]
