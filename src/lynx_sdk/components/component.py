"""
Component base class for Lynx. A Component is any entity that has endpoints and can communicate via MQTT.
Both Service and Channel inherit from Component.
"""



# === IMPORTS ===

# -stdlib Imports-
from abc import ABC, abstractmethod
from typing import Dict, Optional
from logging import Logger, getLogger
from enum import Enum

# -Lynx Imports-
from lynx_sdk.models.endpoint import Endpoint
from lynx_sdk.singletons.time_source import TimeSource
from lynx_sdk.utils.mqtt_client import MqttClient

# -External Imports-


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class ComponentType(Enum):
    NODE = "Node"
    SERVICE = "Service"
    CHANNEL = "Channel"


class Component(ABC):
    """
    Base class for Lynx components (Service, Channel, etc).
    
    A Component represents any entity in Lynx that:
    - Has identity (id, title, description)
    - Has endpoints for communication
    - Has a time source for timestamps
    - Has a logger for diagnostics
    - Can produce an "about" description of itself
    
    This is an abstract base class and cannot be instantiated directly.
    Use Service or Channel instead.
    """
    
    def __init__(
        self,
        id: str,
        component_type: ComponentType,
        title: str,
        description: str,
        lynx_version: str,
        time_source: TimeSource,
        logger: Logger,
        emit_logs_as_notices: bool,
        client: MqttClient):
        """
        Initialize a Lynx Component.
        
        Args:
            id: Unique identifier for this component
            component_type: Type of component (SERVICE, CHANNEL, etc)
            title: Human-readable title
            description: Human-readable description
            lynx_version: Lynx protocol version this component uses
            time_source: Time source for timestamps (None if component doesn't need one)
            logger: Logger for this component (defaults to logger named after id)
        """
        self.id: str = id
        self.component_type: ComponentType = component_type
        self.title: str = title
        self.description: str = description
        self.lynx_version: str = lynx_version
        self.time_source: TimeSource = time_source
        self.logger: Logger = logger
        self.emit_logs_as_notices: bool = emit_logs_as_notices,
        self.client: MqttClient = client
        self.endpoints: Dict[str, Endpoint] = {}
    
    
    @abstractmethod
    def produce_about(self) -> Dict:
        """
        Produce a dictionary describing this component.
        
        This base implementation provides common fields that all components share.
        Subclasses can override this method to add component-specific information.
        
        Returns:
            Dictionary containing:
            - type: Component type (service, channel, etc)
            - docs: Documentation fields (title, description, version, time_source)
            - config: Configuration information (empty by default)
            - status: Status information (empty by default)
            - endpoints: Dictionary of endpoint information
        """
        about_dict = {
            "type": self.component_type.value.lower(),
            "docs": {
                "title": self.title,
                "description": self.description,
                "lynx_version": self.lynx_version,
            },
            "config": {},
            "status": {},
            "endpoints": {
                endpoint.topic: endpoint.produce_about() 
                for endpoint in self.endpoints.values()
            }
        }
        
        # Only include time_source if component has one
        if self.time_source is not None:
            about_dict["docs"]["time_source"] = self.time_source.time_source_type.value
        
        return about_dict


# === MAIN LOOP ===


