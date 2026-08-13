"""
This module provides an endpoint for Lynx.
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from typing import Callable, Optional, Any, Dict, List
from enum import Enum
from logging import Logger
from lynx_sdk.utils.mqtt_client import MqttClient, InboundMessage

# -Lynx Imports-
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
        payload_schema: object,
        logger: Logger,
        mqtt_client: MqttClient,
        payload_schema_additional_properties: bool = False,
        description: str = ""):
        """
        Initialize a Lynx Endpoint object.

        Args:
            topic: The full topic path of the endpoint. e.g. "Service/Channel/?/About"
            endpoint_direction: The direction of the endpoint (SUB, PUB, or PUBSUB)
            logger: Logger for this endpoint,
            mqtt_client: MqttClient for this endpoint,
            payload_schema: JSON schema for the payload. For PUB endpoints, this is what is sent. For SUB endpoints, this is what is received.
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
        self.payload_schema: object = payload_schema
        self.logger: Logger = logger
        self.mqtt_client: MqttClient = mqtt_client
        self.payload_schema_additional_properties: bool = payload_schema_additional_properties
        self.description: str = description


    def validate_payload(self, payload_dict: Dict) -> bool:
        """
        Validate a payload dictionary against a JSON schema.
        """
        try:
            validate_json_object(payload_dict, self.payload_schema, additional_properties=self.payload_schema_additional_properties)
            return True
        except jsonschema.exceptions.ValidationError as e:
            self.logger.warning(f"Payload validation failed for endpoint '{self.topic}': {e.message}")
            return False
            
    

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


class InEndpoint(Endpoint):
    def __init__(self,
        topic: str,
        handler: Callable[[InboundMessage], Optional[Any]],
        logger: Logger,
        mqtt_client: MqttClient,
        payload_schema: object,
        description: str = "",
        payload_schema_additional_properties: bool = False,
        reply_topics: Optional[List[str]] = None,
        data_output: Optional[bool] = None):
        """
        Initialize a Lynx Subscribe Endpoint object.
        
        Args:
            topic: MQTT topic to subscribe to
            handler: Callback function to handle received messages
            component: The Component (Service or Channel) this endpoint belongs to
            payload_schema: JSON schema for validating received payloads
            description: Human-readable description
            reply_topics: Optional list of absolute MQTT topics that each receive one
                nominal non-data reply. None = undeclared; [] = explicitly no reply.
            data_output: Optional bool indicating whether this endpoint may publish to
                the channel's < topic. None = undeclared; True/False = explicit declaration.
                Only valid on Channel InEndpoints.
        """
        super().__init__(
            topic=topic, 
            endpoint_direction=LynxEndpointDirection.SUB,
            logger=logger,
            mqtt_client=mqtt_client,
            payload_schema=payload_schema, 
            description=description,
            payload_schema_additional_properties=payload_schema_additional_properties)
        self.handler: Callable[[InboundMessage], Optional[Any]] = handler
        self.reply_topics: Optional[List[str]] = reply_topics
        self.data_output: Optional[bool] = data_output
        self.mqtt_client.add_callback(topic=self.topic, callback=self.callback)


    def callback(self, mqtt_client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> Optional[Any]:
        """
        Handle an incoming MQTT message by parsing JSON bytes and calling the handler.
        
        This method:
        1. Parses the MQTT payload bytes as JSON
        2. Validates the payload against the schema (if one exists)
        3. Builds an InboundMessage and calls the handler
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
            self.logger.debug(f"Handling payload for endpoint '{self.topic}': {message.payload}")
            
            stripped_payload = message.payload.strip()

            # Parse JSON bytes to dictionary
            if len(stripped_payload) == 0:
                stripped_payload = "{}" # Default to an empty dictionary if the payload is empty
            try:
                payload: Dict = orjson.loads(stripped_payload)
            except orjson.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON payload for endpoint '{self.topic}': {e}")
                raise ValueError(f"Invalid JSON payload: {e}") from e
            
            # Validate payload against schema if schema exists
            if self.payload_schema is not None and len(payload) > 0:
                if not self.validate_payload(payload):
                    # TODO - consider returning an error message or publishing to an error topic instead of just returning None
                    return

            # Build contextual message and call the handler
            try:
                incoming_message = MqttClient.from_paho_message(message=message, payload=payload)
                return self.handler(incoming_message)
            except Exception as e:
                self.logger.exception(
                    f"Handler exception for endpoint '{self.topic}': "
                    f"{type(e).__name__}: {str(e)}"
                )
        except Exception as e:
            self.logger.exception(
                f"Error in callback for endpoint '{self.topic}': "
                f"{type(e).__name__}: {str(e)}"
            )


    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the endpoint, including
        replyTopics and dataOutput when declared.
        """
        about_dict = super().produce_about()

        if self.reply_topics is not None:
            about_dict["replyTopics"] = self.reply_topics

        if self.data_output is not None:
            about_dict["dataOutput"] = self.data_output

        return about_dict


class OutEndpoint(Endpoint):
    def __init__(self,
        topic: str,
        logger: Logger,
        mqtt_client: MqttClient,
        payload_schema: object,
        description: str = "",
        default_qos: int = 0,
        default_retain: bool = False,
        payload_schema_additional_properties: bool = False):
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
            logger=logger,
            mqtt_client=mqtt_client,
            payload_schema=payload_schema, 
            description=description,
            payload_schema_additional_properties=payload_schema_additional_properties)
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
        
        if self.payload_schema is not None and len(payload) > 0:
            if not self.validate_payload(payload):
                return
        
        return self.mqtt_client.publish(
            topic=self.topic,
            payload=payload,
            qos=qos,
            retain=retain,
            properties=properties or {},
            add_timestamp=True
        )