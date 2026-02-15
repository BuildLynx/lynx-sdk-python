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
    from lynx_sdk.components.service import Service
from lynx_sdk.utils.json_tools import validate_json_object

# -External Imports-
import paho.mqtt.client as mqtt
import orjson



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
        payload_schema: object,
        service: Service,
        description: str = "",
        logger: Optional[Logger] = None):
        """
        Initialize a Lynx Endpoint object.

        Args:
            topic (str): The full topic path of the endpoint. e.g. "Service/Channel/?/About"
            description (str): The description of the endpoint. 
                e.g. "The client is asked for the current time according to its clock"
            service (Service): The service that the endpoint interfaces with.
            endpoint_direction (LynxEndpointDirection): The direction of the endpoint. 
                e.g. LynxEndpointDirection.SUB
            payload_schema (object): The schema for the payload of the endpoint. If the endpoint_direction is 
                LynxEndpointDirection.PUB, the payload is what is sent from the endpoint. If the endpoint_direction is 
                LynxEndpointDirection.SUB, the payload is what is received at the endpoint. 
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
        """
        self.topic: str = topic
        self.endpoint_direction: LynxEndpointDirection = endpoint_direction
        self.service: Service = service
        self.description: str = description
        self.payload_schema: object = payload_schema
        self.logger: Logger = logger or getLogger(__name__)


    def validate_payload(self, payload_dict: Dict) -> None:
        """
        Validate a payload dictionary against a JSON schema.
        """
        if not validate_json_object(payload_dict, self.payload_schema):
            error_msg = f"Payload validation failed for endpoint '{self.topic}'"
            self.logger.warning(f"{error_msg}. Payload: {payload_dict}")
            raise ValueError(error_msg)
    

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
        payload_schema: object,
        service: Service,
        description: str = "",
        allow_run_while_busy: bool = True,
        logger: Optional[Logger] = None):
        """
        Initialize a Lynx Subscribe Endpoint object.
        """
        super().__init__(
            topic=topic, 
            endpoint_direction=LynxEndpointDirection.SUB, 
            payload_schema=payload_schema, 
            service=service, 
            description=description, 
            logger=logger)
        self.handler: Callable = handler
        self.allow_run_while_busy: bool = allow_run_while_busy


    def callback(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> Optional[Any]:
        """
        Handle an incoming MQTT message by parsing JSON bytes and calling the handler.
        
        This method:
        1. Parses the MQTT payload bytes as JSON
        2. Validates the payload against the schema (if one exists)
        3. Calls the handler function with the parsed dictionary
        4. Handles errors gracefully with logging
        
        Args:
            payload (bytes): The raw MQTT message payload as bytes
            
        Returns:
            Optional[Any]: The return value from the handler, or None if an error occurred
            
        Raises:
            ValueError: If the payload cannot be parsed as JSON
            ValueError: If the payload fails schema validation (when schema exists)
        """
        self.logger.debug(f"Handling payload for endpoint '{self.topic}': {message.payload}")
        
        if self.endpoint_direction == LynxEndpointDirection.PUB:
            self.logger.info(f"This is a pub endpoint: {self.topic}")
            return None
        
        # Parse JSON bytes to dictionary
        try:
            payload_dict: Dict = orjson.loads(message.payload)
        except orjson.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON payload for endpoint '{self.topic}': {e}")
            raise ValueError(f"Invalid JSON payload: {e}") from e
        
        # Validate payload against schema if schema exists
        if self.payload_schema is not None and len(payload_dict) > 0:
            self.validate_payload(payload_dict)

        # Call the handler with the parsed dictionary
        try:
            return self.handler(payload_dict)
        except Exception as e:
            self.logger.exception(
                f"Handler exception for endpoint '{self.topic}': "
                f"{type(e).__name__}: {str(e)}"
            )


class PubEndpoint(Endpoint):
    def __init__(self,
        topic: str,
        payload_schema: object,
        service: Service,
        description: str = "",
        default_qos: int = 0,
        default_retain: bool = False,
        logger: Optional[Logger] = None):
        """
        Initialize a Lynx Publish Endpoint object.
        """
        super().__init__(
            topic=topic, 
            endpoint_direction=LynxEndpointDirection.PUB, 
            payload_schema=payload_schema, 
            service=service, 
            description=description, 
            logger=logger)
        self.default_qos: int = default_qos
        self.default_retain: bool = default_retain
    

    def publish(
        self, 
        payload: Dict, 
        qos: Optional[int] = None, 
        retain: Optional[bool] = None,
        properties: Dict[str, str] = {}) -> mqtt.MQTTMessage:
        """
        Publish a payload using the endpoint.
        """
        if qos is None:
            qos = self.default_qos
        if retain is None:
            retain = self.default_retain
        
        return self.service.publish_using_endpoint(
            endpoint=self, 
            payload=payload,
            qos=qos,
            retain=retain,
            properties=properties)