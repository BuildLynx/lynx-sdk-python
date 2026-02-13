"""
DESCRIPTION
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import Callable, Dict, List, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import itertools

# -Lynx Imports-
from lynx_sdk.models.endpoint import Endpoint,SubEndpoint, PubEndpoint
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
        client: mqtt.Client,
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
        self.client: mqtt.Client = client
        self.poll_function: Callable = poll_function
        self.start_stream_function: Callable = start_stream_function
        self.data_schema: Dict = output_data_schema
        self.lynx_version: str = lynx_version
        self.time_source: TimeSource = time_source

        # -Endpoints-
        self.endpoints: Dict[str, Endpoint] = {}

        if isinstance(poll_function, Callable):
            self.endpoints["!/Poll"] = SubEndpoint(
                topic=f"!/Poll",
                handler=self.poll_handler,
                description="Poll the channel for data.",
                payload_schema=POLL_PAYLOAD_SCHEMA)

        if isinstance(start_stream_function, Callable):
            self.endpoints["!/Stream"] = SubEndpoint(
                topic=f"!/Stream",
                handler=self.stream_handler,
                description="Poll the channel for data.",
                payload_schema=POLL_PAYLOAD_SCHEMA)
        
        if isinstance(poll_function, Callable) or isinstance(start_stream_function, Callable):
            self.endpoints["!/Stop"] = SubEndpoint(
                topic=f"!/Stop",
                handler=self.stop,
                description="Stop the channel.",
                payload_schema={})

        if self.data_schema is not None:
            self.endpoints["<"] = PubEndpoint(
                topic=f"<",
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
        self.endpoints["<"].publish(data_list, self.client)


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
            self.id:{
                "title": self.title,
                "description": self.description,
            }
        }
# === MAIN LOOP ===


