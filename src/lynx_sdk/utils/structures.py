"""
Components are the building blocks of the Lynx SDK.
"""



# === IMPORTS ===

# -stdlib Imports-
from enum import Enum

# -Lynx Imports-

# -External Imports-



# === CONSTANTS ===

LYNX_VERSION = "A-01.01"


# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class QualityOfService(Enum):
    AT_LEAST_ONCE = 0
    AT_MOST_ONCE = 1
    EXACTLY_ONCE = 2

class RetainFlag(Enum):
    TRUE = True
    FALSE = False

class LynxConfig():
    pass


# === MAIN LOOP ===


