"""
This module provides an endpoint for Lynx.

Generative AI was used in the Creation/Modification of this file.

Endpoint is a transport binding around a pure EndpointSpec. The spec owns the
advertised schema and About metadata; the binding owns the MQTT client, logger,
and subscribe/publish behavior.
"""

from __future__ import annotations
from typing import Callable, Optional, Any, Dict, List
from logging import Logger

from lynx_sdk.messaging.mqtt_client import MqttClient, InboundMessage
from lynx_sdk.protocol.endpoint_spec import EndpointSpec, LynxEndpointDirection

import paho.mqtt.client as mqtt
import orjson
import jsonschema


class Endpoint:
    def __init__(
        self,
        spec: EndpointSpec,
        logger: Logger,
        mqtt_client: MqttClient):
        """
        Bind an EndpointSpec to a logger and MQTT client.
        """
        self.spec: EndpointSpec = spec
        self.logger: Logger = logger
        self.mqtt_client: MqttClient = mqtt_client

    @property
    def topic(self) -> str:
        return self.spec.topic

    @property
    def endpoint_direction(self) -> LynxEndpointDirection:
        return self.spec.endpoint_direction

    @property
    def payload_schema(self) -> Optional[Dict]:
        return self.spec.payload_schema

    @property
    def description(self) -> str:
        return self.spec.description

    def validate_payload(self, payload_dict: Dict) -> bool:
        """
        Validate a payload against this endpoint's canonical schema.
        Failures are logged and return False; they are not raised.
        """
        try:
            self.spec.validate_payload(payload_dict)
            return True
        except jsonschema.exceptions.ValidationError as e:
            self.logger.warning(f"Payload validation failed for endpoint '{self.topic}': {e.message}")
            return False

    def produce_about(self) -> Dict:
        return self.spec.produce_about()


def _build_spec(
    topic: str,
    endpoint_direction: LynxEndpointDirection,
    payload_schema: Optional[Dict] = None,
    payload_properties: Optional[Dict] = None,
    additional_properties: bool = False,
    description: str = "",
    reply_topics: Optional[List[str]] = None,
    data_output: Optional[bool] = None) -> EndpointSpec:
    return EndpointSpec(
        topic=topic,
        endpoint_direction=endpoint_direction,
        payload_schema=payload_schema,
        payload_properties=payload_properties,
        additional_properties=additional_properties,
        description=description,
        reply_topics=reply_topics,
        data_output=data_output)


class InEndpoint(Endpoint):
    def __init__(self,
        topic: str,
        handler: Callable[[InboundMessage], Optional[Any]],
        logger: Logger,
        mqtt_client: MqttClient,
        payload_schema: Optional[Dict] = None,
        payload_properties: Optional[Dict] = None,
        description: str = "",
        additional_properties: bool = False,
        reply_topics: Optional[List[str]] = None,
        data_output: Optional[bool] = None):
        """
        Initialize a Lynx Subscribe Endpoint object.
        """
        spec = _build_spec(
            topic=topic,
            endpoint_direction=LynxEndpointDirection.SUB,
            payload_schema=payload_schema,
            payload_properties=payload_properties,
            additional_properties=additional_properties,
            description=description,
            reply_topics=reply_topics,
            data_output=data_output)
        super().__init__(spec=spec, logger=logger, mqtt_client=mqtt_client)
        self.handler: Callable[[InboundMessage], Optional[Any]] = handler
        self.mqtt_client.add_callback(topic=self.topic, callback=self.callback)

    @property
    def reply_topics(self) -> Optional[List[str]]:
        return self.spec.reply_topics

    @property
    def data_output(self) -> Optional[bool]:
        return self.spec.data_output

    def callback(self, mqtt_client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> Optional[Any]:
        """
        Handle an incoming MQTT message by parsing JSON bytes and calling the handler.
        """
        try:
            self.logger.debug(f"Handling payload for endpoint '{self.topic}': {message.payload}")

            stripped_payload = message.payload.strip()

            if len(stripped_payload) == 0:
                stripped_payload = b"{}"
            try:
                payload: Dict = orjson.loads(stripped_payload)
            except orjson.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON payload for endpoint '{self.topic}': {e}")
                raise ValueError(f"Invalid JSON payload: {e}") from e

            if self.payload_schema is not None and len(payload) > 0:
                if not self.validate_payload(payload):
                    return

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


class OutEndpoint(Endpoint):
    def __init__(self,
        topic: str,
        logger: Logger,
        mqtt_client: MqttClient,
        payload_schema: Optional[Dict] = None,
        payload_properties: Optional[Dict] = None,
        description: str = "",
        default_qos: int = 0,
        default_retain: bool = False,
        additional_properties: bool = False):
        """
        Initialize a Lynx Publish Endpoint object.
        """
        spec = _build_spec(
            topic=topic,
            endpoint_direction=LynxEndpointDirection.PUB,
            payload_schema=payload_schema,
            payload_properties=payload_properties,
            additional_properties=additional_properties,
            description=description)
        super().__init__(spec=spec, logger=logger, mqtt_client=mqtt_client)
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
