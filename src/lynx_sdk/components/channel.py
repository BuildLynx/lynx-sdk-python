"""
Channel class for Lynx. A Channel is the encapsulation of a single input and/or output data stream.
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from typing import Callable, Dict, List, Any, Optional, TYPE_CHECKING
from copy import deepcopy
import threading
import time
import itertools
from functools import partial
from dataclasses import dataclass

# -Lynx Imports-
from lynx_sdk.components.component import Component, ComponentType
from lynx_sdk.models.endpoint import SubEndpoint, PubEndpoint
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
import jsonschema


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



# === CLASSES ===

class PayloadBuilder:
    def __init__(self, contents: Dict[str, Any] | bool, paginate: int, out_data_endpoint: PubEndpoint, service: Service):
        self.contents = contents
        self.data_list: List[Dict[str, Any]] = []
        self.perf_counter = time.perf_counter_ns()
        self.paginate = paginate
        self.out_data_endpoint = out_data_endpoint
        self.service = service
    
    def add_data(self, data: Any):
        if len(self.data_list) == 0:
            self.perf_counter = time.perf_counter_ns()
            current_perf_counter_diff = 0
        else:
            current_perf_counter_diff = time.perf_counter_ns()-self.perf_counter
        
        if self.contents is not True:
            try:
                data = trim_payload_by_contents(data, self.contents)
            except PayloadBuildingError as e:
                self.service.logger.error(f"Error trimming payload: {e.message}")
                return
        
        self.data_list.append({
            "s": current_perf_counter_diff // int(1e9),
            "ns": current_perf_counter_diff % int(1e9),
            "data": data
        })

        if len(self.data_list) >= self.paginate:
            self.publish()
    

    def publish(self):
        if len(self.data_list) == 0:
            return
        self.out_data_endpoint.publish(payload=self.data_list)
        self.data_list = []
        self.perf_counter = time.perf_counter_ns()


class Channel(Component):
    def __init__(self,
        id: str,
        service: Service,
        title: str = "",
        description: str = "",
        poll_function: Optional[Callable] = None,
        stream_function: Optional[Callable] = None,
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
        self._stream_function: Optional[Callable] = stream_function
        self._exit_flag: Optional[threading.Event] = None # Flag to signal polling/streaming thread to exit

        # -Endpoints-
        # Note: Channel no longer has ?/About, @/About, or @/Notice endpoints
        # These are redundant with Service's endpoints

        if isinstance(poll_function, Callable):
            self.cmd_poll_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_POLL_ENDPOINT_ARGS,
                sub_handler=self.poll_handler)

        if isinstance(stream_function, Callable):
            self.cmd_stream_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_STREAM_ENDPOINT_ARGS,
                sub_handler=self.start_stream_handler)
            self.cmd_stop_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_STOP_ENDPOINT_ARGS,
                sub_handler=self.stop_handler)

        if output_data_schema is not None:
            channel_out_data_schema = deepcopy(CHANNEL_OUT_DATA_ENDPOINT_ARGS)
            channel_out_data_schema["payload_schema"]["items"]["properties"]["data"]["properties"] = output_data_schema
            self.out_data_endpoint: PubEndpoint = self.new_endpoint(PubEndpoint, channel_out_data_schema)


    def get_service(self) -> "Service":
        """
        Get the parent Service that owns resources.
        """
        return self.service
    
    
    # @classmethod
    # def from_dict(
    #     cls, 
    #     channel_dict: Dict,
    #     service: "Service",
    #     poll_function: Optional[Callable] = None,
    #     start_stream_function: Optional[Callable] = None) -> "Channel":
    #     """
    #     Initialize a Lynx Channel object from a dictionary.
    #     """
    #     return cls(
    #         id=channel_dict["id"],
    #         service=service,
    #         title=channel_dict["title"],
    #         description=channel_dict["description"],
    #         poll_function=poll_function,
    #         start_stream_function=start_stream_function,
    #         output_data_schema=channel_dict.get("output_data_schema"),
    #         lynx_version=channel_dict.get("lynx_version", LYNX_VERSION))


    def poll_handler(self, payload: Dict):
        """
        Handle a poll request.
        """
        contents = payload.get("contents", True)

        #TODO - validate the contents dict against the endpoint's schema before starting the stream

        data = self._poll_function()
        
        if contents is not True:
            try:
                data = trim_payload_by_contents(data, contents)
            except PayloadBuildingError as e:
                self.service.logger.error(f"Error trimming payload: {e.message}")
                return
        
        payload = [{"s": 0, "ns": 0, "data": data}]

        self.out_data_endpoint.publish(payload=payload)


    def start_stream_handler(self, payload: Dict):
        """
        Handle a stream start request by starting a thread that calls the start stream function with a callback to queue the stream data.
         The start stream function should call the callback with each new piece of data to be published.
        """
        contents = payload.get("contents", True)
        num_samples = payload.get("numSamples", 0)
        paginate = payload.get("paginate", num_samples)
        if paginate == 0:
            paginate = num_samples

        #TODO - validate the contents dict against the endpoint's schema before starting the stream

        self._exit_flag = threading.Event() # Create a new exit flag for this streaming session
        payload_builder = PayloadBuilder(contents=contents, paginate=paginate, out_data_endpoint=self.out_data_endpoint, service=self.service)
        stream_thread = threading.Thread(target=self._stream_handler, kwargs={"req_payload": payload, "payload_builder": payload_builder, "num_samples": num_samples, "exit_flag": self._exit_flag})
        stream_thread.start()

    
    def _stream_handler(self, req_payload: Dict, payload_builder: PayloadBuilder, num_samples: int, exit_flag: threading.Event):
        """
        Handle a stream request.
        """
        samples_processed = 0
        for data in self._stream_function(req_payload=req_payload, exit_flag=exit_flag):
            if num_samples > 0 and samples_processed >= num_samples:
                break
            if exit_flag.wait(timeout=0.001):
                break
            payload_builder.add_data(data)
            samples_processed += 1
    
        payload_builder.publish()
        self._exit_flag.set()
        self._exit_flag = None
        #self.set_status(state=ComponentState.STOPPED)


    def stop_handler(self, payload: Dict):
        """
        Stop the channel's polling/streaming.
        """
        self._exit_flag.set()


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
