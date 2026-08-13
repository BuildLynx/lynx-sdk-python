"""
Default logger construction for Lynx client components.

Generative AI was used in the Creation/Modification of this file.
"""

import logging
import sys
from typing import Optional


def configure_logger(component_id: str, logger: Optional[logging.Logger] = None) -> logging.Logger:
    """Return the given logger, or a stdout DEBUG logger named after the component."""
    if logger is not None:
        return logger
    configured = logging.getLogger(component_id)
    configured.setLevel(level=logging.DEBUG)
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(level=logging.DEBUG)
    configured.addHandler(stream_handler)
    configured.propagate = False
    return configured
