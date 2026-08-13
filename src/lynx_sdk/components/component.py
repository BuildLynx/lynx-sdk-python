"""
Component base class for Lynx. A Component is any entity that has identity, endpoints, and can produce info about itself.
Both Service and Channel inherit from Component.

Generative AI was used in the Creation/Modification of this file.

This class holds identity, endpoint registry, and status. It does not own an
MQTT client or publish About: those are runtime concerns of ClientComponent
and of Channel's parent Service.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Optional, Type, Callable, Any
from enum import Enum
from copy import copy
from logging import Logger

from lynx_sdk.models.endpoint import Endpoint, InEndpoint, OutEndpoint
from lynx_sdk.models.endpoint_args import REPLY_TOPIC_CLIENT_ABOUT
from lynx_sdk.protocol.topics import about_topic, build_topic
from lynx_sdk.protocol.capabilities import InterfaceFrozenError
from lynx_sdk.utils.mqtt_client import MqttClient


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

    Logger and MQTT client are injected by the runtime owner (a ClientComponent,
    or a Channel's parent Service). Topic strings are built from owner_id, not
    by branching on runtime type beyond Channel nesting.
    """

    def __init__(
        self,
        id: str,
        component_type: ComponentType,
        title: str,
        description: str,
        lynx_version: str,
        owner_id: Optional[str] = None,
        logger: Optional[Logger] = None,
        mqtt_client: Optional[MqttClient] = None):
        """
        Initialize a Lynx Component.

        Args:
            id: Unique identifier for this component
            component_type: Type of component (SERVICE, CHANNEL, etc)
            title: Human-readable title
            description: Human-readable description
            lynx_version: Lynx protocol version this component uses
            owner_id: MQTT namespace owner. Channels pass their Service id;
                Services and Nodes default to their own id.
            logger: Logger used by endpoints. Required before creating endpoints.
            mqtt_client: MQTT client used by endpoints. Required before creating endpoints.
        """
        self.id: str = id
        self.component_type: ComponentType = component_type
        self.title: str = title
        self.description: str = description
        self.lynx_version: str = lynx_version
        self._owner_id: str = owner_id if owner_id is not None else id
        self.logger: Optional[Logger] = logger
        self.mqtt_client: Optional[MqttClient] = mqtt_client

        self.endpoints: Dict[str, Endpoint] = {}
        self._status: Dict[str, Any] = {}
        self._interface_frozen: bool = False

    @abstractmethod
    def produce_about(self) -> Dict:
        """Produce a dictionary describing this component."""
        pass

    def freeze_interface(self) -> None:
        """
        Lock the advertised endpoint set and schemas.

        Called before the first @/About publish (A2.1 section 4.7). Subsequent
        attempts to add endpoints or attach sources raise InterfaceFrozenError.
        """
        self._interface_frozen = True

    def require_mutable_interface(self, action: str = "modify the interface") -> None:
        if self._interface_frozen:
            raise InterfaceFrozenError(
                f"Cannot {action} on {self.component_type.value} '{self.id}' after its "
                "interface was frozen (first @/About publish)."
            )

    def get_status(self) -> Dict[str, Any]:
        return self._status

    def get_status_dict(self) -> Dict[str, Any]:
        return copy(self._status)

    def set_status(self, **status_updates: Any) -> bool:
        """
        Update status fields in memory. Does not publish.

        Returns:
            True if any field changed.
        """
        changed_status = False
        for key, value in status_updates.items():
            if key not in self._status or self._status[key] != value:
                self._status[key] = value
                changed_status = True
        return changed_status

    def _create_endpoint(
        self,
        endpoint_class: Type[Endpoint],
        sub_handler: Optional[Callable] = None,
        **endpoint_args: Any) -> Endpoint:
        """
        Create a new endpoint for this component from a dictionary of arguments.
        """
        self.require_mutable_interface("add an endpoint")
        if self.logger is None or self.mqtt_client is None:
            raise RuntimeError(
                f"Component '{self.id}' has no logger/mqtt_client; cannot bind endpoints. "
                "Attach a Service (for Channels) or construct a ClientComponent first."
            )

        endpoint_args = dict(endpoint_args)
        endpoint_args["logger"] = self.logger
        endpoint_args["mqtt_client"] = self.mqtt_client

        skip_prefixes = bool(endpoint_args.pop("skip_topic_prefixes", False))
        nested_id = self.id if self.component_type == ComponentType.CHANNEL else None
        endpoint_args["topic"] = build_topic(
            self._owner_id,
            endpoint_args["topic"],
            nested_id=nested_id,
            skip_prefixes=skip_prefixes)

        if issubclass(endpoint_class, InEndpoint):
            endpoint_args["handler"] = sub_handler
            reply_topics = endpoint_args.get("reply_topics")
            if reply_topics is not None:
                resolved_about = about_topic(self._owner_id)
                endpoint_args["reply_topics"] = [
                    resolved_about if t == REPLY_TOPIC_CLIENT_ABOUT else t
                    for t in reply_topics
                ]

        endpoint = endpoint_class(**endpoint_args)
        self.endpoints[endpoint.topic] = endpoint
        return endpoint

    def new_in_endpoint(
        self,
        sub_handler: Callable,
        **endpoint_args: Any) -> InEndpoint:
        """Create a new InEndpoint for this component."""
        return self._create_endpoint(InEndpoint, sub_handler, **endpoint_args)

    def new_out_endpoint(self, **endpoint_args: Any) -> OutEndpoint:
        """Create a new OutEndpoint for this component."""
        return self._create_endpoint(OutEndpoint, **endpoint_args)
