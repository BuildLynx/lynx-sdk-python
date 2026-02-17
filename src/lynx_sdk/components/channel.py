"""
Channel class for Lynx. A Channel is the encapsulation of a single input and/or output data stream.
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from typing import Callable, Dict, List, Any, Optional, TYPE_CHECKING
import threading
import time
import itertools
import copy
from enum import Enum
import logging
import sys

# -Lynx Imports-
from lynx_sdk.components.component import Component, ComponentType
from lynx_sdk.models.endpoint import Endpoint, SubEndpoint, PubEndpoint
from lynx_sdk.models.endpoint_args import \
    CHANNEL_CMD_POLL_ENDPOINT_ARGS, \
    CHANNEL_CMD_STREAM_ENDPOINT_ARGS, \
    CHANNEL_CMD_STOP_ENDPOINT_ARGS, \
    CHANNEL_OUT_DATA_ENDPOINT_ARGS
from lynx_sdk.utils.json_tools import validate_json_schema, trim_payload_by_contents, PayloadBuildingError
from lynx_sdk.utils.structures import LYNX_VERSION

if TYPE_CHECKING:
    from lynx_sdk.components.service import Service

# -External Imports-
import paho.mqtt.client as mqtt
import jsonschema


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



# === CLASSES ===


class Channel(Component):
    def __init__(self,
        id: str,
        service: Service,
        title: str = "",
        description: str = "",
        poll_function: Optional[Callable] = None,
        start_stream_function: Optional[Callable] = None,
        output_data_schema: Optional[Dict] = None,
        lynx_version: str = LYNX_VERSION):
        """
        Initialize a Lynx Channel object.
        
        Args:
            id: Unique identifier for this channel
            service: Parent service this channel belongs to
            title: Human-readable title
            description: Human-readable description
            poll_function: Function to call for polling data
            start_stream_function: Function to call to start streaming data
            output_data_schema: JSON schema for the channel's output data
            lynx_version: Lynx protocol version
        """
        # Validate output data schema if provided
        if output_data_schema is not None:
            try:
                validate_json_schema(output_data_schema)
            except jsonschema.exceptions.ValidationError as e:
                pass
        
        # Initialize Component base class
        super().__init__(
            id=id,
            component_type=ComponentType.CHANNEL,
            title=title,
            description=description,
            lynx_version=lynx_version
        )
        
        # -Channel-specific initialization-
        self.service: Service = service
        self._poll_function: Optional[Callable] = poll_function
        self._start_stream_function: Optional[Callable] = start_stream_function
        self.last_payload: Dict = {}

        # -Endpoints-
        # Note: Channel no longer has ?/About, @/About, or @/Notice endpoints
        # These are redundant with Service's endpoints

        if isinstance(poll_function, Callable):
            self.cmd_poll_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_POLL_ENDPOINT_ARGS,
                sub_handler=self.poll_handler)

        if isinstance(start_stream_function, Callable):
            self.cmd_stream_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_STREAM_ENDPOINT_ARGS,
                sub_handler=self.stream_handler)
        
        if isinstance(poll_function, Callable) or isinstance(start_stream_function, Callable):
            self.cmd_stop_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_STOP_ENDPOINT_ARGS,
                sub_handler=self.stop_handler)

        if output_data_schema is not None:
            channel_out_data_schema = CHANNEL_OUT_DATA_ENDPOINT_ARGS.copy()
            channel_out_data_schema["payload_schema"]["items"]["properties"]["data"]["properties"] = output_data_schema
            self.out_data_endpoint = self.new_endpoint(PubEndpoint, channel_out_data_schema)


    def get_service(self) -> "Service":
        """
        Get the parent Service that owns resources.
        """
        return self.service
    
    
    @classmethod
    def from_dict(
        cls, 
        channel_dict: Dict,
        service: "Service",
        poll_function: Optional[Callable] = None,
        start_stream_function: Optional[Callable] = None) -> "Channel":
        """
        Initialize a Lynx Channel object from a dictionary.
        """
        return cls(
            id=channel_dict["id"],
            service=service,
            title=channel_dict["title"],
            description=channel_dict["description"],
            poll_function=poll_function,
            start_stream_function=start_stream_function,
            output_data_schema=channel_dict.get("output_data_schema"),
            lynx_version=channel_dict.get("lynx_version", LYNX_VERSION))
    

    def repeat_polling(self, 
        num_samples: int, 
        interval: float, 
        return_data: List[Dict[str, Any]], 
        contents: Dict[str, Any] | bool = True):
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

            if contents is not True:
                try:
                    data = trim_payload_by_contents(data, contents)
                except PayloadBuildingError as e:
                    self.service.logger.error(f"Error trimming payload: {e.message}")
                    return

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
        contents = payload.get("contents", True)
        data_list = []
        poll_thread = threading.Thread(target=self.repeat_polling, args=(num_samples, interval, data_list, contents))
        poll_thread.start()
        poll_thread.join()
        self.out_data_endpoint.publish(payload=data_list)


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


    def stop_handler(self):
        """
        Stop the channel.
        """
        pass


    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the channel.
        """
        return {
            "lynxType": "channel",
            "docs": {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "lynx_version": self.lynx_version,
            },
            "config": {},
            "status": self.get_status_dict(),
            "endpoints": {
                endpoint.topic: endpoint.produce_about() for endpoint in self.endpoints.values()
            }
        }
# === MAIN LOOP ===


