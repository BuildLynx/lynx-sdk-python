"""
TimeSource class for Lynx. A TimeSource is the encapsulation of a single time source, it contains a function to get
    the current time in seconds and nanoseconds according to the time source.

Generative AI was used in the Creation/Modification of this file.
"""

from typing import Callable, Dict, Optional
import time
from enum import Enum

from lynx_sdk.protocol.time_units import NS_PER_S


EPOCH_DELTA_1970_TO_2000 = 946684800   # 30 years incl leap days


class TimeSourceType(Enum):
    PROCESS = "process"
    UNIX = "unix"


class TimeSource():
    def __init__(
        self,
        time_source_type: TimeSourceType,
        get_time_function: Optional[Callable[[], Dict[str, int]]] = None):
        """
        Initialize a TimeSource object.

        Subclasses override get_time(). A custom callable may be supplied instead.
        """
        self.time_source_type: TimeSourceType = time_source_type
        self._get_time_function = get_time_function

    def get_time(self) -> Dict[str, int]:
        if self._get_time_function is not None:
            return self._get_time_function()
        raise NotImplementedError


class ProcessPerfTimeSource(TimeSource):
    def __init__(self):
        self._start_time: float = time.perf_counter_ns()
        super().__init__(time_source_type=TimeSourceType.PROCESS)

    def get_time(self) -> Dict[str, int]:
        current_time = time.perf_counter_ns()-self._start_time
        return {
            "s": current_time // NS_PER_S,
            "ns": current_time % NS_PER_S
        }


class UnixTimeSource(TimeSource):
    def __init__(self):
        super().__init__(time_source_type=TimeSourceType.UNIX)

    def get_time(self) -> Dict[str, int]:
        current_time = time.time_ns()
        return {
            "s": current_time // NS_PER_S,
            "ns": current_time % NS_PER_S
        }


class Epoch2000TimeSource(TimeSource):
    """
    Many MicroPython implementations use a 2000-01-01 epoch.
    https://docs.micropython.org/en/latest/library/time.html
    """
    def __init__(self):
        super().__init__(time_source_type=TimeSourceType.UNIX)

    def get_time(self) -> Dict[str, int]:
        current_time = time.time_ns()
        return {
            "s": (current_time // NS_PER_S) + EPOCH_DELTA_1970_TO_2000,
            "ns": current_time % NS_PER_S
        }


def instantiate_ideal_time_source() -> TimeSource:
    """
    Determine the ideal time source for the current system. Ideally all timestamps should be in reference to Unix epoch. However, some MicroPython implementations use a 2000-01-01 epoch, and other devices might not have a standard epoch at all.
    """
    start_year = time.gmtime(0)[0]
    if start_year == 1970:
        return UnixTimeSource()
    elif start_year == 2000:
        return Epoch2000TimeSource()
    else:
        return ProcessPerfTimeSource()
