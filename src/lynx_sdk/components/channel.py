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
    GET_ABOUT_ENDPOINT_ARGS, \
    SYS_ABOUT_ENDPOINT_ARGS, \
    SYS_NOTICE_ENDPOINT_ARGS, \
    CHANNEL_CMD_POLL_ENDPOINT_ARGS, \
    CHANNEL_CMD_STREAM_ENDPOINT_ARGS, \
    CHANNEL_CMD_STOP_ENDPOINT_ARGS, \
    CHANNEL_OUT_DATA_ENDPOINT_ARGS
from lynx_sdk.models.time_source import TimeSource
from lynx_sdk.utils.json_tools import validate_json_schema, generate_full_data_schema
from lynx_sdk.utils.structures import LYNX_VERSION
from lynx_sdk.models.notice import LoggingNoticeHandler

if TYPE_CHECKING:
    from lynx_sdk.components.service import Service

# -External Imports-
import paho.mqtt.client as mqtt
import jsonschema


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



# === CLASSES ===

class ChannelState(Enum):
    BUSY = "busy"
    IDLE = "idle"
    DISCONNECTED = "disconnected"
    DISABLED = "disabled"


class ChannelStatus():
    def __init__(self):
        self.action: str = ""
        self.state: ChannelState = ChannelState.IDLE


class Channel(Component):
    def __init__(self,
        id: str,
        service: Service,
        title: str = "",
        description: str = "",
        poll_function: Optional[Callable] = None,
        start_stream_function: Optional[Callable] = None,
        output_data_schema: Optional[Dict] = None,
        lynx_version: str = LYNX_VERSION,
        time_source: Optional[TimeSource] = None,
        publish_logs_as_notices: Optional[bool] = None,
        logger: Optional[logging.Logger] = None):
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
            time_source: Time source for timestamps (defaults to service's time source)
        """
        # Validate output data schema if provided
        if output_data_schema is not None:
            try:
                validate_json_schema(output_data_schema)
            except jsonschema.exceptions.ValidationError as e:
                pass

        if time_source is None:
            time_source = service.time_source
        
        if publish_logs_as_notices is None:
            publish_logs_as_notices = service.publish_logs_as_notices
        
        # Initialize Component base class with channel-specific logger
        if logger is None:
            logger: logging.Logger = logging.getLogger(f"{service.id}.{id}")
            logger.setLevel(level=logging.DEBUG)
            stream_handler = logging.StreamHandler(stream=sys.stdout)
            stream_handler.setLevel(level=logging.DEBUG)
            logger.addHandler(stream_handler)
            logger.propagate = False
        
        super().__init__(
            id=id,
            component_type=ComponentType.CHANNEL,
            title=title,
            description=description,
            lynx_version=lynx_version,
            time_source=time_source,
            logger=logger,
            publish_logs_as_notices=publish_logs_as_notices,
            client=service.client,
            topic_prefix=f"{service.id}/{id}"
        )
        
        # -Channel-specific initialization-
        self.service: Service = service
        self._poll_function: Optional[Callable] = poll_function
        self._start_stream_function: Optional[Callable] = start_stream_function
        self.last_payload: Dict = {}

        # -Endpoints-
        self.get_about_endpoint = self.new_endpoint(SubEndpoint, GET_ABOUT_ENDPOINT_ARGS,
            lambda args: self.sys_about_endpoint.publish(payload=self.produce_about()))
        self.sys_about_endpoint = self.new_endpoint(PubEndpoint, SYS_ABOUT_ENDPOINT_ARGS)
        self.sys_notice_endpoint = self.new_endpoint(PubEndpoint, SYS_NOTICE_ENDPOINT_ARGS)

        if isinstance(poll_function, Callable):
            self.cmd_poll_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_POLL_ENDPOINT_ARGS,
                self.poll_handler)

        if isinstance(start_stream_function, Callable):
            self.cmd_stream_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_STREAM_ENDPOINT_ARGS,
                self.stream_handler)
        
        if isinstance(poll_function, Callable) or isinstance(start_stream_function, Callable):
            self.cmd_stop_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_STOP_ENDPOINT_ARGS,
                self.stop_handler)

        if output_data_schema is not None:
            channel_out_data_schema = CHANNEL_OUT_DATA_ENDPOINT_ARGS.copy()
            channel_out_data_schema["payload_schema"]["items"]["properties"]["data"]["properties"] = output_data_schema
            self.out_data_endpoint = self.new_endpoint(PubEndpoint, channel_out_data_schema)
        
        # -Setup logging with notices-
        if self.publish_logs_as_notices:
            self.logger.addHandler(LoggingNoticeHandler(endpoint=self.sys_notice_endpoint))


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
        contents = payload.get("contents", True)
        start_time = self.time_source.get_time()
        data_list = []
        poll_thread = threading.Thread(target=self.repeat_polling, args=(num_samples, interval, data_list))
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
        return super().produce_about()
# === MAIN LOOP ===


