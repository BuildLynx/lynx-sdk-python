"""
Notice payload types for Lynx @/Notice.

Generative AI was used in the Creation/Modification of this file.
"""

from enum import Enum
from dataclasses import dataclass, field


class NoticeSeverity(Enum):
    """Mimics Python logging levels, redefined so the wire enum is stable."""
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
