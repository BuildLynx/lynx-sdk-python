"""
This module provides an endpoint for Lynx.
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from logging import Logger, getLogger
from typing import Callable, Optional, Any, Dict, TYPE_CHECKING
from enum import Enum

# -Lynx Imports-
if TYPE_CHECKING:
    from lynx_sdk.components.component import Component, ComponentState
from lynx_sdk.utils.json_tools import validate_json_object

# -External Imports-
import paho.mqtt.client as mqtt
import orjson
import jsonschema



# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class LynxEndpointDirection(Enum):
    SUB = "sub"
    PUB = "pub"
    PUBSUB = "pubsub"


class Endpoint:
    def __init__(self,
        topic: str,
        endpoint_direction: LynxEndpointDirection,
        component: Component,
        payload_schema: object,
        description: str = ""):
        """
        Initialize a Lynx Endpoint object.

        Args:
            topic: The full topic path of the endpoint. e.g. "Service/Channel/?/About"
            endpoint_direction: The direction of the endpoint (SUB, PUB, or PUBSUB)
            component: The Component (Service or Channel) this endpoint belongs to
            payload_schema: JSON schema for the payload. For PUB endpoints, this is what is sent.
                For SUB endpoints, this is what is received.
                e.g. {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "type": "object",
                    "properties": {
                        "time": {
                            "type": "string"
                        }
                    }
                } 
                or alternatively, e.g. {
                    "time": {
                        "type": "string"
                    }
                }
            description: Human-readable description of the endpoint
        """
        self.topic: str = topic
        self.endpoint_direction: LynxEndpointDirection = endpoint_direction
        self.component: Component = component
        self.payload_schema: object = payload_schema
        self.description: str = description


    def validate_payload(self, payload_dict: Dict) -> None:
        """
        Validate a payload dictionary against a JSON schema.
        """
        try:
            validate_json_object(payload_dict, self.payload_schema)
        except jsonschema.exceptions.ValidationError as e:
            raise ValueError(f"JSON object validation failed: {e.message}")
            
    

    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the endpoint.
        """
        about_dict = {
            "endpoint_direction": self.endpoint_direction.value,
        }

        if self.description is not None:
            about_dict["description"] = self.description
        
        about_dict["payload_schema"] = self.payload_schema

        return about_dict


class SubEndpoint(Endpoint):
    def __init__(self,
        topic: str,
        handler: Callable,
        component: Component,
        payload_schema: object,
        description: str = "",
        allow_run_while_busy: bool = True):
        """
        Initialize a Lynx Subscribe Endpoint object.
        
        Args:
            topic: MQTT topic to subscribe to
            handler: Callback function to handle received messages
            component: The Component (Service or Channel) this endpoint belongs to
            payload_schema: JSON schema for validating received payloads
            description: Human-readable description
            allow_run_while_busy: Whether to allow execution while busy
        """
        super().__init__(
            topic=topic, 
            endpoint_direction=LynxEndpointDirection.SUB,
            component=component,
            payload_schema=payload_schema, 
            description=description)
        self.handler: Callable = handler
        self.allow_run_while_busy: bool = allow_run_while_busy
        self.component.client.add_callback(topic=self.topic, callback=self.callback)


    def callback(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> Optional[Any]:
        """
        Handle an incoming MQTT message by parsing JSON bytes and calling the handler.
        
        This method:
        1. Parses the MQTT payload bytes as JSON
        2. Validates the payload against the schema (if one exists)
        3. Calls the handler function with the parsed dictionary
        4. Handles errors gracefully with logging
        
        Args:
            client: MQTT client instance
            userdata: User data passed to callback
            message: MQTT message containing topic and payload
            
        Returns:
            Optional[Any]: The return value from the handler, or None if an error occurred
            
        Raises:
            ValueError: If the payload cannot be parsed as JSON
            ValueError: If the payload fails schema validation (when schema exists)
        """
        try:
            self.component.status["state"] = ComponentState.BUSY
            self.component.status["action"] = self.topic
            self.component.logger.debug(f"Handling payload for endpoint '{self.topic}': {message.payload}")
            
            # Parse JSON bytes to dictionary
            try:
                payload: Dict = orjson.loads(message.payload)
            except orjson.JSONDecodeError as e:
                self.component.logger.error(f"Failed to parse JSON payload for endpoint '{self.topic}': {e}")
                raise ValueError(f"Invalid JSON payload: {e}") from e
            
            # Validate payload against schema if schema exists
            if self.payload_schema is not None and len(payload) > 0:
                self.validate_payload(payload)

            # Call the handler with the parsed dictionary
            try:
                return self.handler(payload)
            except Exception as e:
                self.component.logger.exception(
                    f"Handler exception for endpoint '{self.topic}': "
                    f"{type(e).__name__}: {str(e)}"
                )
        except Exception as e:
            self.component.logger.exception(
                f"Error in callback for endpoint '{self.topic}': "
                f"{type(e).__name__}: {str(e)}"
            )
        finally:
            self.component.set_status(state=ComponentState.IDLE, action="")


class PubEndpoint(Endpoint):
    def __init__(self,
        topic: str,
        component: Component,
        payload_schema: object,
        description: str = "",
        default_qos: int = 0,
        default_retain: bool = False,
        validate_payload: bool = True):
        """
        Initialize a Lynx Publish Endpoint object.
        
        Args:
            topic: MQTT topic to publish to
            component: The Component (Service or Channel) this endpoint belongs to
            payload_schema: JSON schema for validating outgoing payloads
            description: Human-readable description
            default_qos: Default Quality of Service level (0, 1, or 2)
            default_retain: Default retain flag
        """
        super().__init__(
            topic=topic, 
            endpoint_direction=LynxEndpointDirection.PUB,
            component=component,
            payload_schema=payload_schema, 
            description=description)
        self.default_qos: int = default_qos
        self.default_retain: bool = default_retain
    

    def publish(
        self, 
        payload: Dict, 
        qos: Optional[int] = None, 
        retain: Optional[bool] = None,
        properties: Dict[str, str] = {}) -> mqtt.MQTTMessage:
        """
        Publish a payload using this endpoint.
        
        Args:
            payload: Dictionary payload to publish (will be JSON-encoded)
            qos: Quality of Service level (defaults to endpoint's default_qos)
            retain: Retain flag (defaults to endpoint's default_retain)
            properties: Additional MQTT v5 user properties
            
        Returns:
            MQTTMessageInfo from the publish operation
        """
        if qos is None:
            qos = self.default_qos
        if retain is None:
            retain = self.default_retain
        
        if self.validate_payload and self.payload_schema is not None and len(payload) > 0:
            self.validate_payload(payload)
        
        return self.component.client.publish(
            topic=self.topic,
            payload=payload,
            qos=qos,
            retain=retain,
            properties=properties)