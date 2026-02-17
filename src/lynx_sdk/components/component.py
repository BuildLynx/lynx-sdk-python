"""
Component base class for Lynx. A Component is any entity that has endpoints and can communicate via MQTT.
Both Service and Channel inherit from Component.
"""



# === IMPORTS ===

# -stdlib Imports-
from abc import ABC, abstractmethod
from typing import Dict, Optional, Type, Callable, Any
from logging import Logger
from enum import Enum
from copy import deepcopy

# -Lynx Imports-
from lynx_sdk.models.endpoint import Endpoint, SubEndpoint, PubEndpoint
from lynx_sdk.models.time_source import TimeSource
from lynx_sdk.utils.mqtt_client import MqttClient
from lynx_sdk.utils.datastructures import deep_merge

# -External Imports-


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class ComponentType(Enum):
    NODE = "Node"
    SERVICE = "Service"
    CHANNEL = "Channel"


class ComponentState(Enum):
    BUSY = "busy"
    IDLE = "idle"
    DISCONNECTED = "disconnected"
    DISABLED = "disabled"


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
        time_source: Optional[TimeSource],
        logger: Logger,
        publish_logs_as_notices: bool,
        client: MqttClient,
        topic_prefix: str):
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
            publish_logs_as_notices: Whether to publish log messages as Notices to MQTT
            client: MQTT client for this component
            topic_prefix: Prefix for the topics of the component (e.g. "service_id/channel_id")
        """
        self.id: str = id
        self.component_type: ComponentType = component_type
        self.title: str = title
        self.description: str = description
        self.lynx_version: str = lynx_version
        self.time_source: Optional[TimeSource] = time_source
        self.logger: Logger = logger
        self.publish_logs_as_notices: bool = publish_logs_as_notices,
        self.client: MqttClient = client
        self.topic_prefix: str = topic_prefix

        self.endpoints: Dict[str, Endpoint] = {}
        self._status: Dict[str, Any] = {
            "state": ComponentState.IDLE,
            "action": ""
        }
    
    
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
            "docs": {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "lynx_version": self.lynx_version,
                "type": self.component_type.value.lower(),
            },
            "config": {},
            "status": self.get_status(),
            "endpoints": {
                endpoint.topic: endpoint.produce_about() for endpoint in self.endpoints.values()
            }
        }
        
        # Only include time_source if component has one
        if self.time_source is not None:
            about_dict["docs"]["time_source"] = self.time_source.time_source_type.value
        
        return about_dict
    

    def get_status(self) -> Dict[str, Any]:
        """
        Get the status of the component.
        """
        return self._status
    

    def set_status(self, 
        state: Optional[ComponentState] = None, 
        action: Optional[str] = None, 
        about_endpoint: Optional[PubEndpoint] = None) -> Dict[str, Any]:
        """
        Set the status of the component. 
        Args:
            state: The state of the component.
            action: The action of the component.
            about_endpoint: If provided, the status will be published to this endpoint. 
                To not publish the status change, do not provide this argument.
        Returns:
            The status of the component.
        """
        changed_status = False
        if state is not None and state != self._status["state"]:
            self._status["state"] = state
            changed_status = True
        if action is not None and action != self._status["action"]:
            self._status["action"] = action
            changed_status = True
        if changed_status and about_endpoint is not None:
            # if self.type == ComponentType.SERVICE:
            about_endpoint.publish(payload={})
        return self._status

    
    def new_endpoint(self, 
        endpoint_class: Type[Endpoint], 
        endpoint_args: Dict, 
        sub_handler: Optional[Callable] = None) -> Endpoint:
        """
        Create a new endpoint for the service from a dictionary of arguments. 
        """
        endpoint_args = endpoint_args.copy()
        endpoint_args["component"] = self
        endpoint_args["topic"] = self.topic_prefix + endpoint_args["topic"]
        if issubclass(endpoint_class, SubEndpoint):
            endpoint_args["handler"] = sub_handler
        endpoint = endpoint_class(**endpoint_args)
        self.endpoints[endpoint.topic] = endpoint
        return endpoint


# === MAIN LOOP ===


