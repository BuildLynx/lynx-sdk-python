"""
MQTT will-message / notice bridge: publish Python log records as Lynx Notices.

Generative AI was used in the Creation/Modification of this file.
"""

from __future__ import annotations
import logging

from lynx_sdk.messaging.endpoint import OutEndpoint
from lynx_sdk.protocol.notice import Notice, NoticeSeverity


class LoggingNoticeHandler(logging.Handler):
    """
    A logging.Handler that publishes notices to MQTT using a Lynx OutEndpoint.
    """

    def __init__(self, endpoint: OutEndpoint, min_level: NoticeSeverity = NoticeSeverity.INFO):
        super().__init__(level=min_level.value)
        self.endpoint: OutEndpoint = endpoint

    def notice_from_record(self, record: logging.LogRecord, action: str = "") -> Notice:
        """Build and return a Notice from a LogRecord."""
        return Notice(
            action=action,
            severity=NoticeSeverity(record.levelno).name,
            message=record.getMessage(),
            data={})

    def emit(self, record: logging.LogRecord) -> None:
        """Override logging.Handler.emit to publish a Notice on the notice endpoint."""
        notice: Notice = self.notice_from_record(record)
        sec: int = int(record.created)
        nsec: int = int((record.created - sec) * 1e9)
        self.endpoint.publish(payload=notice.__dict__, properties={"s": str(sec), "ns": str(nsec)})
