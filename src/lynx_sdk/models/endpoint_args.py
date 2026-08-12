"""
This module provides the arguments for the endpoints for components including Component and Channel.
"""

from lynx_sdk.utils.structures import LYNX_VERSION
from lynx_sdk.utils.datastructures import deep_merge
from lynx_sdk.models.notice import NoticeSeverity

REPLY_TOPIC_CLIENT_ABOUT = "__CLIENT_ABOUT__"

# -Component Endpoints-
GET_ABOUT_ENDPOINT_ARGS = {
    "topic": "?/About",
    "description": "Query information about the Component.",
    "reply_topics": [REPLY_TOPIC_CLIENT_ABOUT],
    "payload_schema": {
        "contents": {
            "title": "contents Object",
            "description": "Refer to Lynx standard contents argument for details.",
            "default": {},
            "type": ["object", "boolean"]
        }
    }
}

SYS_ABOUT_ENDPOINT_ARGS = {
    "topic": "@/About",
    "description": "Publish information about the Component.",
    "default_qos": 1,
    "default_retain": True,
    "payload_schema": {
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
    "payload_schema": {
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
    "payload_schema": {
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
    "payload_schema_additional_properties": True,
    "payload_schema": SYS_ABOUT_ENDPOINT_ARGS["payload_schema"]
}

# -Service Endpoints-
SERVICE_SYS_ABOUT_ENDPOINT_ARGS = deep_merge(SYS_ABOUT_ENDPOINT_ARGS, {
    "payload_schema": {
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
    "description": "Start polling at a set time interval on the channel for data.",
    "reply_topics": [],
    "data_output": True,
    "payload_schema": {
        "contents": {
            "title": "Values to contents",
            "description": "Default everything to true if empty",
            "default": {},
            "type": ["object", "boolean"]
        }
    }
}

CHANNEL_CMD_STREAM_ENDPOINT_ARGS = {
    "topic": "!/Stream",
    "description": "Start streaming on the channel, emitting data when available.",
    "reply_topics": [REPLY_TOPIC_CLIENT_ABOUT],
    "data_output": True,
    "payload_schema": {
        "contents": {
            "title": "Values to contents",
            "description": "Default everything to true if empty",
            "default": {},
            "type": ["object", "boolean"]
        },
        "interval": {
            "title": "Sample Interval",
            "description": "Seconds between samples",
            "default": 1.0,
            "type": "number",
            "minimum": 0
        },
        "numSamples": {
            "title": "Number of Samples",
            "description": "1 for single, 0 for infinite, positive int for numbered, default 0",
            "default": 0,
            "type": "integer",
            "minimum": 0
        },
        "paginate": {
            "title": "Paginate",
            "description": "0 for no pagination (all data in one payload), positive int for page size, default 1",
            "default": 1,
            "type": "integer",
            "minimum": 0
        }
    }
}

CHANNEL_CMD_STOP_ENDPOINT_ARGS = {
    "topic": "!/Stop",
    "description": "Stop polling or streaming on the channel.",
    "reply_topics": [REPLY_TOPIC_CLIENT_ABOUT],
    "data_output": False,
    "payload_schema": {}
}

CHANNEL_OUT_DATA_ENDPOINT_ARGS = {
    "topic": "<",
    "description": "Output data from the channel.",
    "default_qos": 0,
    "default_retain": False,
    "payload_schema": {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "s": {
                    "title": "Seconds",
                    "description": "Seconds since the start of the channel",
                    "type": "integer"
                },
                "ns": {
                    "title": "Nanoseconds",
                    "description": "Nanoseconds since the start of the channel",
                    "type": "integer"
                },
                "data": {
                    "title": "Data",
                    "description": "The data from the channel",
                    "type": "object",
                    "properties": {}
                }
            }
        }
    }
}