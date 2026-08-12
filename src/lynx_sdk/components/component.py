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
from enum import Enum
from copy import copy

# -Lynx Imports-
from lynx_sdk.models.endpoint import Endpoint, InEndpoint, OutEndpoint
from lynx_sdk.models.endpoint_args import REPLY_TOPIC_CLIENT_ABOUT

if TYPE_CHECKING:
    from lynx_sdk.components.service import Service
    from lynx_sdk.components.client_component import ClientComponent

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
    - Has identity (id, title, description, version)
    - Has endpoints for communication  
    - Can produce an "about" description of itself
    - Can track status (shape varies by component type)
    
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
        # Subclasses initialize the concrete status shape (e.g. connected vs command).
        self._status: Dict[str, Any] = {}
    
    
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
    def get_client_component(self) -> ClientComponent:
        """
        Get the ClientComponent that owns resources (MQTT client, time_source, logger).
        """
        pass

    def get_status(self) -> Dict[str, Any]:
        """
        Get the status of the component.
        """
        return self._status
    

    def get_status_dict(self) -> Dict[str, Any]:
        """
        Get the status of the component as a dictionary suitable for About payloads.
        """
        return copy(self._status)
    

    def set_status(self, about_endpoint: Optional[OutEndpoint] = None, **status_updates: Any) -> Dict[str, Any]:
        """
        Update status fields and optionally publish a partial About.
        
        Args:
            about_endpoint: If provided, publish the updated status to this endpoint.
            **status_updates: Status keys to set (e.g. connected=True, command=None).
        
        Returns:
            The status of the component.
        """
        changed_status = False
        for key, value in status_updates.items():
            if key not in self._status or self._status[key] != value:
                self._status[key] = value
                changed_status = True
        if changed_status and about_endpoint is not None:
            status_payload = self.get_status_dict()
            if self.component_type == ComponentType.CHANNEL:
                payload = {"channels": {self.id: {"status": status_payload}}}
            else:
                payload = {"status": status_payload}
            about_endpoint.publish(payload=payload)
        return self._status
    
    
    def _create_endpoint(self, 
        endpoint_class: Type[Endpoint], 
        sub_handler: Optional[Callable] = None,
        **endpoint_args: Dict) -> Endpoint:
        """
        Create a new endpoint for this component from a dictionary of arguments.
        
        This is a convenience method that:
        - Automatically passes component=self
        - Constructs the full topic path from the component's ID
        - Adds the handler for InEndpoints
        - Resolves reply_topics sentinels for InEndpoints
        - Registers the endpoint in self.endpoints
        
        Args:
            endpoint_class: The endpoint class to instantiate (InEndpoint or OutEndpoint)
            endpoint_args: Dictionary of arguments for the endpoint (topic, payload_schema, description, etc.)
            sub_handler: Handler function for InEndpoints
            
        Returns:
            The created endpoint instance
        """
        endpoint_args = endpoint_args.copy()
        endpoint_args["component"] = self
        
        # Construct full topic path
        # Service endpoints: "service_id/?/About"
        # Channel endpoints: "service_id/channel_id/?/About"
        if endpoint_args.pop("skip_topic_prefixes", False):
            endpoint_args["topic"] = endpoint_args['topic']
        elif self.component_type == ComponentType.CHANNEL:
            service: Service = self.get_client_component()
            endpoint_args["topic"] = f"{service.id}/{self.id}/{endpoint_args['topic']}"
        elif self.component_type == ComponentType.SERVICE:
            endpoint_args["topic"] = f"{self.id}/{endpoint_args['topic']}"
        elif self.component_type == ComponentType.NODE:
            endpoint_args["topic"] = endpoint_args['topic']
        else:
            raise ValueError(f"Invalid component type: {self.component_type}")
        
        if issubclass(endpoint_class, InEndpoint):
            endpoint_args["handler"] = sub_handler
            reply_topics = endpoint_args.get("reply_topics")
            if reply_topics is not None:
                client_component = self.get_client_component()
                endpoint_args["reply_topics"] = [
                    client_component.sys_about_endpoint.topic
                    if t == REPLY_TOPIC_CLIENT_ABOUT else t
                    for t in reply_topics
                ]
        
        endpoint = endpoint_class(**endpoint_args)
        self.endpoints[endpoint.topic] = endpoint
        return endpoint
    

    def new_in_endpoint(self,
        sub_handler: Callable,
        **endpoint_args: Dict) -> InEndpoint:
        """
        Create a new sub endpoint for this component from a dictionary of arguments.
        """
        return self._create_endpoint(InEndpoint, sub_handler, **endpoint_args)
    

    def new_out_endpoint(self,
        **endpoint_args: Dict) -> InEndpoint:
        """
        Create a new sub endpoint for this component from a dictionary of arguments.
        """
        return self._create_endpoint(OutEndpoint, **endpoint_args)
