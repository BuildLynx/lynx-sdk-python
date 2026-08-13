"""
This module provides the arguments for the endpoints for components including Component and Channel.

Generative AI was used in the Creation/Modification of this file.

Schemas here are declared as `payload_properties` (a bare map of property name to
subschema) or `payload_schema` (a complete Draft-7 schema carrying a "type"). Endpoint
normalizes whichever is given into canonical form once, at construction. The two are
separate keys rather than one key whose shape is inferred, because a properties map may
legitimately contain a property named "type".
"""

from typing import Dict, Optional

from lynx_sdk.protocol.version import LYNX_VERSION
from lynx_sdk.protocol.dicts import deep_merge
from lynx_sdk.protocol.schema_tools import SchemaDefinitionError
from lynx_sdk.protocol.notice import NoticeSeverity

REPLY_TOPIC_CLIENT_ABOUT = "__CLIENT_ABOUT__"

# -Shared property fragments-
CONTENTS_PROPERTY = {
    "title": "contents Object",
    "description": "Omit or true for the full payload. An empty object {} selects no keys.",
    "default": True,
    "type": ["object", "boolean"]
}

# -Component Endpoints-
GET_ABOUT_ENDPOINT_ARGS = {
    "topic": "?/About",
    "description": "Query information about the Component.",
    "reply_topics": [REPLY_TOPIC_CLIENT_ABOUT],
    "payload_properties": {
        "contents": CONTENTS_PROPERTY
    }
}

SYS_ABOUT_ENDPOINT_ARGS = {
    "topic": "@/About",
    "description": "Publish information about the Component.",
    "default_qos": 1,
    "default_retain": True,
    "payload_properties": {
        "lynxType": {
            "title": "Lynx Component Type",
            "description": "The type of the Lynx Component.",
            "type": "string",
            "enum": ["Node", "Service", "Channel"]
        },
        "docs": {
            "title": "Documentation",
            "description": "Docs cover the immutable metadata of the Component.",
            "type": "object",
            "properties": {
                "id": {
                    "title": "ID",
                    "description": "The unique identifier of the Component.",
                    "type": "string"
                },
                "title": {
                    "title": "Title",
                    "description": "The readable title of the Component.",
                    "type": "string"
                },
                "description": {
                    "title": "Description",
                    "description": "The description of the Component.",
                    "type": "string"
                },
                "lynx_version": {
                    "title": "Lynx Version",
                    "description": "The Lynx protocol version used by the Component.",
                    "type": "string",
                    "enum": [LYNX_VERSION]
                }
            }
        },
        "config": {
            "title": "Configuration",
            "description": "Config covers the mutable configuration of the Component.",
            "type": "object"
        },
        "status": {
            "title": "Status",
            "description": "Status covers the mutable status of the Component. Shape varies by component type.",
            "type": "object"
        },
        "endpoints": {
            "title": "Endpoints",
            "description": "Object representing all the endpoints of the Component.",
            "type": "object"
        }
    }
}

SYS_NOTICE_ENDPOINT_ARGS = {
    "topic": "@/Notice",
    "description": "Publish a notice about the Component.",
    "default_qos": 1,
    "default_retain": False,
    "payload_properties": {
        "action": {
            "title": "Action",
            "description": "The command or query in execution when the notice was published. " \
                + "Empty if not related to a command or query.",
            "type": "string"
        },
        "severity": {
            "title": "Severity",
            "description": "The severity of the notice.",
            "type": "string",
            "enum": [
                NoticeSeverity.DEBUG.name, 
                NoticeSeverity.INFO.name, 
                NoticeSeverity.WARNING.name, 
                NoticeSeverity.ERROR.name, 
                NoticeSeverity.CRITICAL.name]
        },
        "message": {
            "title": "Message",
            "description": "The message of the notice.",
            "type": "string"
        },
        "data": {
            "title": "Data",
            "description": "The data of the notice. Will often be empty.",
            "type": "object"
        }
    }
}

# -Node Endpoints-
NODE_SYS_ABOUT_ENDPOINT_ARGS = deep_merge(SYS_ABOUT_ENDPOINT_ARGS, {
    "payload_properties": {
        "services": {
            "title": "Services",
            "description": "Object representing all the services of the Node.",
            "type": "object"
        },
        "childNodes": {
            "title": "Child Nodes",
            "description": "Object representing all the child nodes of the Node.",
            "type": "object"
        },
        "status": {
            "properties": {
                "connected": {
                    "title": "Connected",
                    "description": "Whether the Node is connected to the Lynx network.",
                    "type": "boolean"
                }
            }
        }
    }
})

SUBSCRIBE_ABOUT_ENDPOINT_ARGS = {
    "skip_topic_prefixes": True,
    "topic": "+/@/About",
    "description": "Monitor about messages from child nodes and services.",
    # Incoming About payloads come from other components, whose Lynx version and
    # extensions this component does not control, so unrecognized keys are accepted.
    "additional_properties": True,
    "payload_properties": SYS_ABOUT_ENDPOINT_ARGS["payload_properties"]
}

# -Service Endpoints-
SERVICE_SYS_ABOUT_ENDPOINT_ARGS = deep_merge(SYS_ABOUT_ENDPOINT_ARGS, {
    "payload_properties": {
        "channels": {
            "title": "Channels",
            "description": "Object representing all the channels of the Component.",
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "status": {
                        "title": "Status",
                        "description": "Status covers the mutable status of the Channel.",
                        "type": "object",
                        "properties": {
                            "command": {
                                "title": "Command",
                                "description": "Active command, or null when idle.",
                                "oneOf": [
                                    {"type": "null"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "command": {
                                                "title": "Command Name",
                                                "description": "The name of the active command.",
                                                "type": "string"
                                            },
                                            "payload": {
                                                "title": "Payload",
                                                "description": "The payload of the active command.",
                                                "type": "object"
                                            }
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        },
        "status": {
            "properties": {
                "connected": {
                    "title": "Connected",
                    "description": "Whether the Service is connected to the Lynx network.",
                    "type": "boolean"
                }
            }
        }
    }
})

# -Channel Endpoints-
CHANNEL_CMD_POLL_ENDPOINT_ARGS = {
    "topic": "!/Poll",
    "description": "Produce one sample immediately.",
    "reply_topics": [],
    "data_output": True,
    "payload_properties": {
        "contents": CONTENTS_PROPERTY
    }
}

CHANNEL_CMD_STREAM_ENDPOINT_ARGS = {
    "topic": "!/Stream",
    "description": "Start streaming on the channel, emitting data when available.",
    "reply_topics": [REPLY_TOPIC_CLIENT_ABOUT],
    "data_output": True,
    "payload_properties": {
        "contents": CONTENTS_PROPERTY,
        "sampleInterval": {
            "title": "Sample Interval",
            "description": "Minimum seconds between admitted samples. Samples offered sooner are discarded. 0 = admit every sample the source offers.",
            "default": 1.0,
            "type": "number",
            "minimum": 0
        },
        "numSamples": {
            "title": "Number of Samples",
            "description": "Total samples to admit into batches. 0 = infinite. Counts only samples admitted after rate and contents filtering.",
            "default": 0,
            "type": "integer",
            "minimum": 0
        },
        "batch": {
            "title": "Batch",
            "description": "Flush limits for the open batch. Omitted object or omitted fields use the field defaults.",
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "maxInterval": {
                    "title": "Max Interval",
                    "description": "Max seconds an open batch may wait before publish. 0 = no time limit (no empty keepalives).",
                    "default": 300,
                    "type": "number",
                    "minimum": 0
                },
                "maxSamples": {
                    "title": "Max Samples",
                    "description": "Max samples per published message. 0 = no count limit.",
                    "default": 1,
                    "type": "integer",
                    "minimum": 0
                }
            }
        }
    }
}

CHANNEL_CMD_STOP_ENDPOINT_ARGS = {
    "topic": "!/Stop",
    "description": "Stop the active command on the channel.",
    "reply_topics": [REPLY_TOPIC_CLIENT_ABOUT],
    "data_output": False,
    # An empty properties map with additionalProperties false accepts only {}. Publishing
    # a bare {} as the schema would advertise the opposite: accept anything.
    "payload_properties": {}
}

SAMPLE_TIMESTAMP_PROPERTIES = {
    "s": {
        "title": "Seconds",
        "description": "Seconds since the start of the current stream",
        "type": "integer"
    },
    "ns": {
        "title": "Nanoseconds",
        "description": "Nanoseconds remainder since the start of the current stream",
        "type": "integer"
    }
}


def build_channel_data_schema(output_data_properties: Optional[Dict] = None) -> Dict:
    """
    Build the `<` payload schema for a channel: an array of timestamped samples whose
    `data` shape is the channel's own.

    The schema is composed from fragments rather than produced by copying a template and
    assigning into a nested path. Deep-path assignment silently accepted a complete schema
    where a properties map was expected, producing a `data` subschema with properties
    named "type" and "properties".

    Args:
        output_data_properties: Map of property name to subschema for the channel's data,
            or None when the channel does not declare its data shape.

    Returns:
        A complete Draft-7 array schema.
    """
    if output_data_properties is None:
        # Shape undeclared: accept any object rather than only the empty object.
        data_schema = {
            "title": "Data",
            "description": "The data from the channel. Shape not declared by this channel.",
            "type": "object"
        }
    else:
        non_schema_keys = [
            name for name, subschema in output_data_properties.items()
            if not isinstance(subschema, (dict, bool))
        ]
        if non_schema_keys:
            raise SchemaDefinitionError(
                f"output_data_schema is a map of property name to subschema, but "
                f"{non_schema_keys} map to values that are not subschemas. "
                f"Pass {{\"load\": {{\"type\": \"number\"}}}}, not "
                f"{{\"type\": \"object\", \"properties\": {{...}}}}."
            )
        data_schema = {
            "title": "Data",
            "description": "The data from the channel",
            "type": "object",
            "properties": output_data_properties,
            "additionalProperties": False
        }

    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                **SAMPLE_TIMESTAMP_PROPERTIES,
                "data": data_schema
            }
        }
    }


def build_channel_out_data_endpoint_args(output_data_properties: Optional[Dict] = None) -> Dict:
    """
    Build the full `<` endpoint args for a channel.

    Args:
        output_data_properties: The channel's data properties map, or None.

    Returns:
        Endpoint args suitable for Component.new_out_endpoint.
    """
    return {
        "topic": "<",
        "description": "Output data from the channel. A JSON array of timestamped samples; an empty array is a valid Stream message.",
        "default_qos": 0,
        "default_retain": False,
        # A complete schema rather than a properties map: the payload is an array, so it
        # cannot be expressed as a map of object properties.
        "payload_schema": build_channel_data_schema(output_data_properties)
    }
