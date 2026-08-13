"""
Pure endpoint declaration: identity, schema, and About metadata.

Generative AI was used in the Creation/Modification of this file.

An EndpointSpec has no MQTT client and no logger. Transport bindings wrap one
and add subscribe/publish. produce_about and validate_payload therefore describe
the same schema (A2.1 section 4.6) without depending on a broker.
"""

from enum import Enum
from typing import Dict, List, Optional

from lynx_sdk.protocol.schema_tools import normalize_payload_schema, validate_json_object


class LynxEndpointDirection(Enum):
    SUB = "sub"
    PUB = "pub"
    PUBSUB = "pubsub"


class EndpointSpec:
    """
    The advertised contract of one MQTT topic: direction, canonical schema, and
    optional replyTopics / dataOutput.
    """

    def __init__(
        self,
        topic: str,
        endpoint_direction: LynxEndpointDirection,
        payload_schema: Optional[Dict] = None,
        payload_properties: Optional[Dict] = None,
        additional_properties: bool = False,
        description: str = "",
        reply_topics: Optional[List[str]] = None,
        data_output: Optional[bool] = None):
        self.topic: str = topic
        self.endpoint_direction: LynxEndpointDirection = endpoint_direction
        self.payload_schema: Optional[Dict] = normalize_payload_schema(
            payload_schema=payload_schema,
            payload_properties=payload_properties,
            additional_properties=additional_properties)
        self.description: str = description
        self.reply_topics: Optional[List[str]] = reply_topics
        self.data_output: Optional[bool] = data_output

    def validate_payload(self, payload_dict: Dict) -> None:
        """
        Validate a payload against the canonical schema.

        Raises:
            jsonschema.exceptions.ValidationError: If the payload does not match.
        """
        if self.payload_schema is None:
            return
        validate_json_object(payload_dict, self.payload_schema)

    def produce_about(self) -> Dict:
        """Endpoint metadata as published under About `endpoints`."""
        about_dict: Dict = {
            "endpoint_direction": self.endpoint_direction.value,
        }
        if self.description is not None:
            about_dict["description"] = self.description
        if self.payload_schema is not None:
            about_dict["payload_schema"] = self.payload_schema
            if "additionalProperties" in self.payload_schema:
                about_dict["additionalProperties"] = self.payload_schema["additionalProperties"]
        if self.reply_topics is not None:
            about_dict["replyTopics"] = self.reply_topics
        if self.data_output is not None:
            about_dict["dataOutput"] = self.data_output
        return about_dict
