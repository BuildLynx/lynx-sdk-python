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
from lynx_sdk.components.component import Component, ComponentType, ComponentState
from lynx_sdk.components.client_component import ClientComponent
from lynx_sdk.models.endpoint import SubEndpoint, PubEndpoint
from lynx_sdk.models.endpoint_args import \
    CHANNEL_CMD_POLL_ENDPOINT_ARGS, \
    CHANNEL_CMD_STREAM_ENDPOINT_ARGS, \
    CHANNEL_CMD_STOP_ENDPOINT_ARGS, \
    CHANNEL_OUT_DATA_ENDPOINT_ARGS
from lynx_sdk.utils.json_tools import validate_json_schema, trim_payload_by_contents, PayloadBuildingError
from lynx_sdk.utils.mqtt_client import InboundMessage
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
    """
    Helper class to build a payload for the channel's output data endpoint, mainly used by Stream channels.
    """
    def __init__(self, contents: Dict[str, Any] | bool, paginate: int, out_data_endpoint: PubEndpoint, service: Service):
        """
        Initialize a PayloadBuilder object.
        Args:
            contents: The contents of the payload.
            paginate: The number of samples to paginate.
            out_data_endpoint: The endpoint to publish the payload to.
            service: The service to use for logging.
        """
        self.contents: Dict[str, Any] | bool = contents
        self.data_list: List[Dict[str, Any]] = []
        self.perf_counter: int = time.perf_counter_ns()
        self.paginate: int = paginate
        self.out_data_endpoint: PubEndpoint = out_data_endpoint
        self.service: Service = service
        self.last_data: Any = None
    
    def add_data(self, data: Any):
        """
        Add data to the payload builder.
        """

        if len(self.data_list) == 0:
            self.perf_counter = time.perf_counter_ns()
            current_perf_counter_diff = 0
        else:
            current_perf_counter_diff = time.perf_counter_ns()-self.perf_counter
        
        if self.contents is not True:
            try:
                data = trim_payload_by_contents(data, self.contents, self.last_data)
                if data == {}: # Data is empty when contents change-of-value values are all the same as last data
                    return
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

        self.last_data = data
        

    def publish(self):
        """
        Publish the payload to the output data endpoint.
        """
        if len(self.data_list) == 0:
            return
        self.out_data_endpoint.publish(payload=self.data_list)
        self.data_list = []
        self.perf_counter = time.perf_counter_ns()


class Channel(Component):
    def __init__(self,
        id: str,
        service: Service,
        sample_function: Callable,
        title: str = "",
        description: str = "",
        output_data_schema: Optional[Dict] = None,
        config: Dict[str, Any] = {"streamOnStartup": False},
        lynx_version: str = LYNX_VERSION):
        """
        Initialize a Lynx Channel object.
        
        Args:
            id: Unique identifier for this channel
            service: Parent service this channel belongs to
            sample_function: Function to call to sample data
            title: Human-readable title
            description: Human-readable description
            output_data_schema: JSON schema for the channel's output data
            config: Configuration for the channel
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
        self._sample_function: Callable[[InboundMessage], Any] = sample_function
        self._exit_flag: Optional[threading.Event] = None # Flag to signal polling/streaming thread to exit

        self.cmd_poll_endpoint = self.new_sub_endpoint(CHANNEL_CMD_POLL_ENDPOINT_ARGS, self.poll_handler)
        self.cmd_stream_endpoint = self.new_sub_endpoint(CHANNEL_CMD_STREAM_ENDPOINT_ARGS, self.start_stream_handler)
        self.cmd_stop_endpoint = self.new_sub_endpoint(CHANNEL_CMD_STOP_ENDPOINT_ARGS, self.stop_handler)

        if output_data_schema is not None:
            channel_out_data_schema = deepcopy(CHANNEL_OUT_DATA_ENDPOINT_ARGS)
            channel_out_data_schema["payload_schema"]["items"]["properties"]["data"]["properties"] = output_data_schema
            self.out_data_endpoint: PubEndpoint = self.new_pub_endpoint(channel_out_data_schema)

        self.config: Dict[str, Any] = config
        if self.config.get("streamOnStartup", False):
            self.start_stream_handler(msg=InboundMessage(payload={"contents": True, "numSamples": 0, "paginate": 1}))


    def get_client_component(self) -> ClientComponent:
        """
        Get the Service that owns resources (MQTT client, time_source, logger).
        """
        return self.service


    def poll_handler(self, msg: InboundMessage):
        """
        Handle a poll request.
        """
        payload = msg.payload
        contents = payload.get("contents", True)

        #TODO - validate the contents dict against the endpoint's schema before starting the stream

        data = self._sample_function(req_payload=payload, continue_sampling=lambda: True) # Assume true because we only sample once
        
        if contents is not True:
            try:
                data = trim_payload_by_contents(data, contents)
            except PayloadBuildingError as e:
                self.service.logger.error(f"Error trimming payload: {e.message}")
                return
        
        payload = [{"s": 0, "ns": 0, "data": data}]

        self.out_data_endpoint.publish(payload=payload)


    def start_stream_handler(self, msg: InboundMessage):
        """
        Handle a stream start request by starting a thread that calls the start stream function with a callback to queue the stream data.
         The start stream function should call the callback with each new piece of data to be published.
        """
        if self._status.get("state") != ComponentState.IDLE:
            self.service.logger.warning(f"Channel '{self.id}' is not idle, ignoring stream start request.")
            return
        
        payload = msg.payload
        contents = payload.get("contents", True)
        num_samples = payload.get("numSamples", 0)
        paginate = payload.get("paginate", num_samples)
        if paginate == 0:
            paginate = num_samples

        #TODO - validate the contents dict against the endpoint's schema before starting the stream

        self._exit_flag = threading.Event() # Create a new exit flag for this streaming session
        payload_builder = PayloadBuilder(contents=contents, paginate=paginate, out_data_endpoint=self.out_data_endpoint, service=self.service)
        stream_thread = threading.Thread(target=self._stream_handler, kwargs={"request": msg, "payload_builder": payload_builder, "num_samples": num_samples})
        stream_thread.start()

    
    def _stream_handler(self, request: Dict, payload_builder: PayloadBuilder, num_samples: int):
        """
        Handle a stream request.
        """
        self.set_status(state=ComponentState.BUSY, action={"command": "Stream", "payload": request.payload})
        samples_processed = 0

        def continue_sampling(default_interval: float = 1.0):
            """
            Determine if the sampling should continue based on the default interval.
            Args:
                default_interval: The default timeout interval in seconds if none is specified in stream request message.
            Returns:
                True if the sampling should continue, False otherwise.
            """
            interval = request.payload.get("interval", default_interval)
            return not self._exit_flag.wait(timeout=interval)

        for data in self._sample_function(request=request, continue_sampling=continue_sampling):
            if num_samples > 0 and samples_processed >= num_samples:
                break
            if self._exit_flag.wait(timeout=0.001):
                break
            payload_builder.add_data(data)
            samples_processed += 1
    
        payload_builder.publish()
        self._exit_flag.set()
        self._exit_flag = None
        self.set_status(state=ComponentState.IDLE, action={"command": "", "payload": {}})


    def stop_handler(self, msg: InboundMessage):
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
    

    def set_status(self, 
        state: Optional[ComponentState] = None, 
        action: Optional[Dict[str, Any]] = None, 
        about_endpoint: Optional[PubEndpoint] = None) -> Dict[str, Any]:
        """
        Set the status of the channel.
        """
        return super().set_status(state=state, action=action, about_endpoint=self.service.sys_about_endpoint)
