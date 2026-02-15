"""
Channel class for Lynx. A Channel is the encapsulation of a single input and/or output data stream.
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from typing import Callable, Dict, List, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass
import threading
import time
import itertools
import copy
from enum import Enum

# -Lynx Imports-
from lynx_sdk.models.endpoint import Endpoint,SubEndpoint, PubEndpoint
from lynx_sdk.singletons.time_source import TimeSource
from lynx_sdk.utils.json_tools import validate_json_schema
from lynx_sdk.utils.structures import LYNX_VERSION
if TYPE_CHECKING:
    from lynx_sdk.components.service import Service

# -External Imports-
import paho.mqtt.client as mqtt
import jsonschema


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
    },
    "paginate": {
        "title": "Paginate",
        "description": "0 for no pagination, positive int for page size, default 0",
        "default": 0,
        "type": "integer",
        "minimum": 0
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
    },
    "paginate": {
        "title": "Paginate",
        "description": "0 for no pagination, positive int for page size, default 0",
        "default": 0,
        "type": "integer",
        "minimum": 0
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
        full_output_data_schema: Dict = copy.deepcopy(OUTPUT_DATA_PAYLOAD_SCHEMA)
        full_output_data_schema["data"]["properties"] = output_data_schema
        return full_output_data_schema



# === CLASSES ===

class ChannelState(Enum):
    BUSY = "busy"
    IDLE = "idle"
    DISABLED = "disabled"


class ChannelStatus():
    def __init__(self):
        self.action: str = ""
        self.state: ChannelState = ChannelState.IDLE


class Channel():
    def __init__(self,
        id: str,
        service: Service,
        title: str = "",
        description: str = "",
        poll_function: Optional[Callable] = None,
        start_stream_function: Optional[Callable] = None,
        output_data_schema: Optional[Dict] = None,
        lynx_version: str = LYNX_VERSION,
        time_source: Optional[TimeSource] = None):
        """
        Initialize a Lynx Channel object.
        """
        if output_data_schema is not None:
            try:
                validate_json_schema(output_data_schema)
            except jsonschema.exceptions.ValidationError as e:
                pass
        
        self.id: str = id
        self.title: str = title
        self.description: str = description
        self.service: Service = service
        self._poll_function: Optional[Callable] = poll_function
        self._start_stream_function: Optional[Callable] = start_stream_function
        self.lynx_version: str = lynx_version
        self.time_source: Optional[TimeSource] = time_source or self.service.time_source
        self.last_payload: Dict = {}

        # -Endpoints-
        get_about_topic: str = f"{self.service.id}/{self.id}/?/About"
        sys_about_topic: str = f"{self.service.id}/{self.id}/@/About"
        self.endpoints: Dict[str, Endpoint] = {
            get_about_topic: SubEndpoint(
                topic=get_about_topic,
                handler=lambda args: self.endpoints[sys_about_topic].publish(payload=self.produce_about()),
                service=self.service,
                description="Get information about the Service.",
                payload_schema={}),
            sys_about_topic: PubEndpoint(
                topic=sys_about_topic,
                description="Emit information about the Service.",
                service=self.service,
                payload_schema={}),
        }

        if isinstance(poll_function, Callable):
            poll_topic = f"{self.service.id}/{self.id}/!/Poll"
            self.endpoints[poll_topic] = SubEndpoint(
                topic=poll_topic,
                handler=self.poll_handler,
                service=self.service,
                description="Poll the channel for data.",
                payload_schema=COMMAND_POLL_PAYLOAD_SCHEMA)

        if isinstance(start_stream_function, Callable):
            stream_topic = f"{self.service.id}/{self.id}/!/Stream"
            self.endpoints[stream_topic] = SubEndpoint(
                topic=stream_topic,
                handler=self.stream_handler,
                service=self.service,
                description="Start the Channel's data stream.",
                payload_schema=COMMAND_STREAM_PAYLOAD_SCHEMA)
        
        if isinstance(poll_function, Callable) or isinstance(start_stream_function, Callable):
            stop_topic = f"{self.service.id}/{self.id}/!/Stop"
            self.endpoints[stop_topic] = SubEndpoint(
                topic=stop_topic,
                handler=self.stop,
                service=self.service,
                description="Stop the channel.",
                payload_schema={})

        if output_data_schema is not None:
            output_data_topic = f"{self.service.id}/{self.id}/<"
            self.endpoints[output_data_topic] = PubEndpoint(
                topic=output_data_topic,
                service=self.service,
                description="Output data",
                payload_schema=generate_full_data_schema(output_data_schema))


    @classmethod
    def from_dict(
        cls, 
        channel_dict: Dict, 
        time_source: Optional[TimeSource] = None, 
        poll_function: Optional[Callable] = None,
        start_stream_function: Optional[Callable] = None) -> "Channel":
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
        Repeat the polling function for the given number of samples and interval. It appends the data to the return_data
            list provided to it. (It does this rather than return since threading calls don't support returns.)
        """
        loop_range = itertools.count() if num_samples == 0 else range(num_samples)
        start_perf_counter = time.perf_counter_ns()
        for idx in loop_range:
            current_perf_counter_diff = time.perf_counter_ns()-start_perf_counter
            if idx == 0:
                current_perf_counter_diff = 0

            data = self._poll_function()

            return_data.append({
                "sec": current_perf_counter_diff // int(1e9),
                "nsec": current_perf_counter_diff % int(1e9),
                "data": data
            })

            time.sleep(interval)


    def poll_handler(self, payload: Dict):
        """
        Handle a poll request.
        """
        num_samples = payload.get("numSamples", 1)
        interval = payload.get("interval", 0)
        include = payload.get("include", True)
        start_time = self.time_source.get_time()
        data_list = []
        poll_thread = threading.Thread(target=self.repeat_polling, args=(num_samples, interval, data_list))
        poll_thread.start()
        poll_thread.join()
        # for data in data_list:
        #     self.output_data_schema.validate(data)
        #     self.output_data_schema.publish(data)
        self.endpoints[f"{self.service.id}/{self.id}/<"].publish(payload=data_list)


    def stream_handler(self, message: mqtt.MQTTMessage):
        """
        Handle a stream start request.
        """
        self._start_stream_function(message, self.stream_callback)
    

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


