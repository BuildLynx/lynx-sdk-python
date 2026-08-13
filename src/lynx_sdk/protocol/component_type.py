"""
Lynx component types as advertised on the wire (lynxType).

Generative AI was used in the Creation/Modification of this file.
"""

from enum import Enum


class ComponentType(Enum):
    NODE = "Node"
    SERVICE = "Service"
    CHANNEL = "Channel"
