"""
TimeSource class for Lynx. A TimeSource is the encapsulation of a single time source, it contains a function to get 
    the current time in seconds and nanoseconds according to the time source.
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import Callable, Dict
import time
from enum import Enum

# -Lynx Imports-

# -External Imports-



# === CONSTANTS ===



# === GLOBALS VARIABLES ===

EPOCH_DELTA_1970_TO_2000 = 946684800   # 30 years incl leap days
NSEC_PER_SEC = int(1e9)


# === FUNCTIONS ===


#  === CLASSES ===

class TimeSourceType(Enum):
    PROCESS = "process"
    UNIX = "unix"



class TimeSource():
    def __init__(self,
        get_time_function: Callable,
        time_source_type: TimeSourceType):
        """
        Initialize a TimeSource object.
        """
        self.get_time: Callable = get_time_function
        self.time_source_type: TimeSourceType = time_source_type



class ProcessPerfTimeSource(TimeSource):
    def __init__(self):
        self._start_time: float = time.perf_counter_ns()
        super().__init__(get_time_function=self.get_time, time_source_type=TimeSourceType.PROCESS)
    

    def get_time(self) -> Dict[int, int]:
        current_time = time.perf_counter_ns()-self._start_time
        return {
            "sec": current_time // NSEC_PER_SEC,
            "nsec": current_time % NSEC_PER_SEC
        }
    

    def reset_start_time(self):
        self._start_time = time.perf_counter_ns()



class UnixTimeSource(TimeSource):
    def __init__(self):
        super().__init__(get_time_function=self.get_time, time_source_type=TimeSourceType.UNIX)
    

    def get_time(self) -> Dict[int, int]:
        current_time = time.time_ns()
        return {
            "sec": current_time // NSEC_PER_SEC,
            "nsec": current_time % NSEC_PER_SEC
        }


class Epoch2000TimeSource(TimeSource):
    """
    Many MicroPython implementations use a 2000-01-01 epoch.
    https://docs.micropython.org/en/latest/library/time.html
    """
    def __init__(self):
        super().__init__(get_time_function=self.get_time, time_source_type=TimeSourceType.UNIX)
    

    def get_time(self) -> Dict[int, int]:
        current_time = time.time_ns()
        return {
            "sec": (current_time // NSEC_PER_SEC) + EPOCH_DELTA_1970_TO_2000,
            "nsec": current_time % NSEC_PER_SEC
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

