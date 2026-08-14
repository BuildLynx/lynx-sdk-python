"""
Channel command concurrency: at most one long-running command at a time.

Generative AI was used in the Creation/Modification of this file.

This is the in-memory backing of status.command from A2.1 section 7.7. It does
not start threads, publish MQTT, or know about Poll vs Stream; callers map its
outcomes onto status and Notices. Poll never uses it, because Poll does not
set status.command.
"""

from typing import Any, Dict, Optional
import threading


class ActiveCommand:
    """
    Idle vs one active long-running command.

    try_begin returns False when a command is already active; the caller MUST
    then leave status and the running command untouched (section 7.7).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._active: Optional[Dict[str, Any]] = None

    def snapshot(self) -> Optional[Dict[str, Any]]:
        """Copy of the active command object, or None when idle."""
        with self._lock:
            if self._active is None:
                return None
            return dict(self._active)

    def is_busy(self) -> bool:
        with self._lock:
            return self._active is not None

    def try_begin(self, command: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """
        Attempt to start a long-running command.

        Returns:
            True if idle and now active, False if rejected.
        """
        with self._lock:
            if self._active is not None:
                return False
            self._active = {"command": command, "payload": payload or {}}
            return True

    def end(self) -> bool:
        """
        Clear the active command.

        Returns:
            True if a command was active, False if already idle.
        """
        with self._lock:
            if self._active is None:
                return False
            self._active = None
            return True
