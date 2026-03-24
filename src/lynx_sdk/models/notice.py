"""
Status is a module-as-singleton for publishing notices at any time
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from enum import Enum
from typing import Optional, Dict, TYPE_CHECKING
import logging
from dataclasses import dataclass, field

# -Lynx Imports-
if TYPE_CHECKING:
    from lynx_sdk.components.service import Service
from lynx_sdk.models.endpoint import PubEndpoint

# -External Imports-
import paho.mqtt.client as mqtt


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

# Notice Severity mimics Python logging levels, but we redefine here in case logging module changes
class NoticeSeverity(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass
class Notice:
    severity: NoticeSeverity
    action: str = field(default="")
    message: str = field(default="")
    data: dict = field(default_factory=dict)


class LoggingNoticeHandler(logging.Handler):
    """
    A logging.Handler (from Python's logging module) that publishes notices to MQTT using a Lynx Service.
    """

    def __init__(self, endpoint: PubEndpoint, min_level: NoticeSeverity = NoticeSeverity.INFO):
        super().__init__(level=min_level.value)
        self.endpoint: PubEndpoint = endpoint


    def notice_from_record(self, record: logging.LogRecord, action: str = "") -> Notice:
        """Build and return a Notice from a LogRecord."""
        return Notice(
            action=action,
            severity=NoticeSeverity(record.levelno).name,
            message=record.getMessage(),
            data={}) # Use a blank dict instead of record.__dict__ to avoid leaking process info


    def emit(self, record: logging.LogRecord) -> None:
        """Override the logging.Handler.emit method to publish a Notice using the Service's notice endpoint."""
        notice: Notice = self.notice_from_record(record)
        sec: int = int(record.created)
        nsec: int = int((record.created - sec) * 1e9)
        self.endpoint.publish(payload=notice.__dict__, properties={"s": str(sec), "ns": str(nsec)})