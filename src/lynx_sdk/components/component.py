"""
Component base class for Lynx. A Component is any entity that has identity, endpoints, and can produce info about itself.
Both Service and Channel inherit from Component.

Note: Service owns the MQTT client, time_source, and logger. Channels access these through their parent Service.
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Optional, Type, Callable, Any, TYPE_CHECKING
from logging import Logger
from enum import Enum
from copy import deepcopy

# -Lynx Imports-
from lynx_sdk.models.endpoint import Endpoint, SubEndpoint, PubEndpoint
from lynx_sdk.utils.datastructures import deep_merge

if TYPE_CHECKING:
    from lynx_sdk.components.service import Service

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
    - Has identity (id, title, description, version)
    - Has endpoints for communication  
    - Can produce an "about" description of itself
    - Can track status (state, action)
    
    Note: MQTT client, time_source, and logger are owned by Service only.
    Channels access these resources through their parent Service reference.
    
    This is an abstract base class and cannot be instantiated directly.
    Use Service or Channel instead.
    """
    
    def __init__(
        self,
        id: str,
        component_type: ComponentType,
        title: str,
        description: str,
        lynx_version: str):
        """
        Initialize a Lynx Component.
        
        Args:
            id: Unique identifier for this component
            component_type: Type of component (SERVICE, CHANNEL, etc)
            title: Human-readable title
            description: Human-readable description
            lynx_version: Lynx protocol version this component uses
        """
        self.id: str = id
        self.component_type: ComponentType = component_type
        self.title: str = title
        self.description: str = description
        self.lynx_version: str = lynx_version

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
        Subclasses must override this method to add component-specific information
        (like time_source for Service, or parent service reference for Channel).
        
        Returns:
            Dictionary containing:
            - docs: Documentation fields (id, title, description, version, type)
            - config: Configuration information
            - status: Status information
            - endpoints: Dictionary of endpoint information
        """
        pass
    

    @abstractmethod
    def get_service(self) -> Service:
        """
        Get the Service that owns resources (MQTT client, time_source, logger).
        For Service, returns self. For Channel, returns parent service.
        """
        pass
    
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the status of the component.
        """
        return self._status
    

    def get_status_dict(self) -> Dict[str, Any]:
        """
        Get the status of the component as a dictionary.
        """
        return {
            "state": self._status["state"].value,
            "action": self._status["action"]
        }
    

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
        Create a new endpoint for this component from a dictionary of arguments.
        
        This is a convenience method that:
        - Automatically passes component=self
        - Constructs the full topic path from the component's ID
        - Adds the handler for SubEndpoints
        - Registers the endpoint in self.endpoints
        
        Args:
            endpoint_class: The endpoint class to instantiate (SubEndpoint or PubEndpoint)
            endpoint_args: Dictionary of arguments for the endpoint (topic, payload_schema, description, etc.)
            sub_handler: Handler function for SubEndpoints
            
        Returns:
            The created endpoint instance
        """
        endpoint_args = endpoint_args.copy()
        endpoint_args["component"] = self
        
        # Construct full topic path
        # Service endpoints: "service_id/?/About"
        # Channel endpoints: "service_id/channel_id/?/About"
        if self.component_type == ComponentType.CHANNEL:
            service = self.get_service()
            endpoint_args["topic"] = f"{service.id}/{self.id}{endpoint_args['topic']}"
        else:
            endpoint_args["topic"] = f"{self.id}{endpoint_args['topic']}"
        
        if issubclass(endpoint_class, SubEndpoint):
            endpoint_args["handler"] = sub_handler
        
        endpoint = endpoint_class(**endpoint_args)
        self.endpoints[endpoint.topic] = endpoint
        return endpoint

    


# === MAIN LOOP ===


