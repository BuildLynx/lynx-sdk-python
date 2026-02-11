"""
DESCRIPTION
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import Callable, Dict, List, Any
from dataclasses import dataclass

# -Lynx Imports-
from lynx_sdk.models.endpoint import Endpoint
from lynx_sdk.singletons.time_source import TimeSource
from lynx_sdk.utils.structures import LYNX_VERSION
from lynx_sdk.models.endpoint import LynxEndpointDirection

# -External Imports-
import paho.mqtt.client as mqtt


# === CONSTANTS ===

POLL_PAYLOAD_SCHEMA = {
    "numSamples": {
        "title": "Number of Samples",
        "description": "1 for single, 0 for infinite, positive int for numbered, default 0",
        "default": 0,
        "type": "integer",
        "minimum": 0
    },
    "interval": {
        "title": "Sample Interval",
        "description": "Seconds between samples",
        "default": 1.0,
        "type": "number",
        "minimum": 0
    },
    "include": {
        "title": "Values to Include",
        "description": "Default everything to true if empty",
        "default": {},
        "type": "object"
    }
}

STREAM_PAYLOAD_SCHEMA = {
    "numSamples": {
        "title": "Number of Samples",
        "description": "1 for single, 0 for infinite, positive int for numbered, default 0",
        "default": 0,
        "type": "integer",
        "minimum": 0
    },
    "include": {
        "title": "Values to Include",
        "description": "Default everything to true if empty",
        "default": {},
        "type": "object"
    }
}



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

@dataclass
class Channel():
    def __init__(self,
        id: str,
        title: str = "",
        description: str = "",
        poll_function: Callable = None,
        start_stream_function: Callable = None,
        output_data_schema: Dict = None,
        lynx_version: str = LYNX_VERSION,
        time_source: TimeSource = None):
        """
        Initialize a Lynx Channel object.
        """
        self.id: str = id
        self.title: str = title
        self.description: str = description
        self.poll_function: Callable = poll_function
        self.start_stream_function: Callable = start_stream_function
        self.output_data_schema: Dict = output_data_schema
        self.lynx_version: str = lynx_version
        self.time_source: TimeSource = time_source

        # -Endpoints-
        self.endpoints: Dict[str, Endpoint] = {}

        if isinstance(poll_function, Callable):
            self.endpoints["poll"] = Endpoint(
                topic=f"{self.id}/!/Poll",
                handler=self.poll_handler,
                endpoint_direction=LynxEndpointDirection.SUB,
                description="Poll the channel for data.",
                payload_schema=POLL_PAYLOAD_SCHEMA)

        if isinstance(start_stream_function, Callable):
            self.endpoints["poll"] = Endpoint(
                topic=f"{self.id}/!/Stream",
                handler=self.stream_handler,
                endpoint_direction=LynxEndpointDirection.SUB,
                description="Poll the channel for data.",
                payload_schema=POLL_PAYLOAD_SCHEMA)
        
        self.endpoints["stop"] = Endpoint(
            topic=f"{self.id}/!/Stop",
            handler=self.stop,
            endpoint_direction=LynxEndpointDirection.SUB,
            description="Stop the channel.",
            payload_schema={})


    @classmethod
    def from_dict(
        cls, 
        channel_dict: Dict, 
        time_source: TimeSource = None, 
        poll_function: Callable = None,
        start_stream_function: Callable = None):
        """
        Initialize a Lynx Channel object from a dictionary.
        """
        return cls(
            id=channel_dict["id"],
            title=channel_dict["title"],
            description=channel_dict["description"],
            poll_function=poll_function,
            start_stream_function=start_stream_function,
            output_data_schema=channel_dict["output_data_schema"],
            lynx_version=channel_dict["lynx_version"],
            time_source=time_source)
    

    def poll_handler(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage):
        """
        Handle a poll request.
        """
        # TODO: For loop through number of samples
        self.poll_function(message)
        # TODO: Publish data through output endpoint


    def stream_handler(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage):
        """
        Handle a poll request.
        """
        self.start_stream_function(message, self.stream_callback)
    

    def stream_callback(self, data: Any):
        """
        Callback for the stream function.
        """
        # TODO: For loop through number of samples/forever
        pass


    def stop(self):
        """
        Stop the channel.
        """
        pass


# === MAIN LOOP ===


