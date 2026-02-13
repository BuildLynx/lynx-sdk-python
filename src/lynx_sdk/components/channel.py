"""
DESCRIPTION
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from typing import Callable, Dict, List, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass
import threading
import time
import itertools

# -Lynx Imports-
from lynx_sdk.models.endpoint import Endpoint,SubEndpoint, PubEndpoint
from lynx_sdk.singletons.time_source import TimeSource
from lynx_sdk.utils.structures import LYNX_VERSION
if TYPE_CHECKING:
    from lynx_sdk.components.service import Service

# -External Imports-
import paho.mqtt.client as mqtt


# === CONSTANTS ===

COMMAND_POLL_PAYLOAD_SCHEMA = {
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

COMMAND_STREAM_PAYLOAD_SCHEMA = {
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

OUTPUT_DATA_PAYLOAD_SCHEMA = {
    "sec": {
        "title": "Seconds",
        "description": "Seconds since the start of the channel",
        "type": "integer"
    },
    "nsec": {
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



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===

def generate_full_data_schema(output_data_schema: Optional[Dict]=None) -> Optional[Dict]:
    """
    Generate a full data schema for the channel.
    """
    if output_data_schema is None:
        return None
    else:
        full_output_data_schema = OUTPUT_DATA_PAYLOAD_SCHEMA
        full_output_data_schema["data"]["properties"] = output_data_schema
        return full_output_data_schema



#  === CLASSES ===

@dataclass
class Channel():
    def __init__(self,
        id: str,
        service: Service,
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
        self.service: Service = service
        self.poll_function: Optional[Callable] = poll_function
        self.start_stream_function: Optional[Callable] = start_stream_function
        self.data_schema: Optional[Dict] = generate_full_data_schema(output_data_schema)
        self.lynx_version: str = lynx_version
        self.time_source: Optional[TimeSource] = time_source

        # -Endpoints-
        self.endpoints: Dict[str, Endpoint] = {}

        if isinstance(poll_function, Callable):
            self.endpoints["!/Poll"] = SubEndpoint(
                topic=f"{self.service.id}/{self.id}/!/Poll",
                handler=self.poll_handler,
                description="Poll the channel for data.",
                payload_schema=COMMAND_POLL_PAYLOAD_SCHEMA)

        if isinstance(start_stream_function, Callable):
            self.endpoints["!/Stream"] = SubEndpoint(
                topic=f"{self.service.id}/{self.id}/!/Stream",
                handler=self.stream_handler,
                description="Poll the channel for data.",
                payload_schema=COMMAND_POLL_PAYLOAD_SCHEMA)
        
        if isinstance(poll_function, Callable) or isinstance(start_stream_function, Callable):
            self.endpoints["!/Stop"] = SubEndpoint(
                topic=f"{self.service.id}/{self.id}/!/Stop",
                handler=self.stop,
                description="Stop the channel.",
                payload_schema={})

        if self.data_schema is not None:
            self.endpoints["<"] = PubEndpoint(
                topic=f"{self.service.id}/{self.id}/<",
                description="Output data",
                payload_schema=self.data_schema)


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
    

    def repeat_polling(self, num_samples: int, interval: float, return_data: List[Dict[str, Any]]):
        """
        Repeat the polling function for the given number of samples and interval.
        """
        loop_range = itertools.count() if num_samples == 0 else range(num_samples)
        start_perf_counter = time.perf_counter_ns()
        for idx in loop_range:
            current_perf_counter_diff = time.perf_counter_ns()-start_perf_counter
            if idx == 0:
                current_perf_counter_diff = 0

            data = self.poll_function()

            return_data.append({
                "sec": current_perf_counter_diff // int(1e9),
                "nsec": current_perf_counter_diff % int(1e9),
                "data": data
            })

            time.sleep(interval)
        print("done polling")


    def poll_handler(self, message: mqtt.MQTTMessage):
        """
        Handle a poll request.
        """
        num_samples = message.get("numSamples", 1)
        interval = message.get("interval", 0)
        include = message.get("include", {True})
        start_time = self.time_source.get_time()
        data_list = []
        poll_thread = threading.Thread(target=self.repeat_polling, args=(num_samples, interval, data_list))
        poll_thread.start()
        poll_thread.join()
        # for data in data_list:
        #     self.output_data_schema.validate(data)
        #     self.output_data_schema.publish(data)
        self.service.publish_using_endpoint(self.endpoints["<"], data_list)


    def stream_handler(self, message: mqtt.MQTTMessage):
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


    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the channel.
        """
        return {
            "type": "channel",
            "docs": {
                "title": self.title,
                "description": self.description,
                "lynx_version": self.lynx_version,
                "time_source": self.time_source.time_source_type.value,
            },
            "config": {},
            "status": {},
            "endpoints": {
                endpoint.topic: endpoint.produce_about() for endpoint in self.endpoints.values()
            },
        }
# === MAIN LOOP ===


