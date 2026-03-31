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

@dataclass
class StreamContext():
    def __init__(self, num_samples: int, contents: Dict[str, Any] | bool, paginate: int):
        self.num_samples = num_samples
        self.contents = contents
        self.paginate = paginate
        self.start_perf_counter = time.perf_counter_ns()
        self.data_list: List[Dict[str, Any]] = []
        self.samples_processed = 0



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
        self._exit_flag: Optional[threading.Event] = None # Flag to signal polling/streaming thread to exit

        # -Endpoints-
        # Note: Channel no longer has ?/About, @/About, or @/Notice endpoints
        # These are redundant with Service's endpoints

        if isinstance(poll_function, Callable):
            self.cmd_poll_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_POLL_ENDPOINT_ARGS,
                sub_handler=self.poll_handler)

        if isinstance(start_stream_function, Callable):
            self.cmd_stream_endpoint = self.new_endpoint(SubEndpoint, CHANNEL_CMD_STREAM_ENDPOINT_ARGS,
                sub_handler=self.start_stream_handler)
        
        if isinstance(poll_function, Callable) or isinstance(start_stream_function, Callable):
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
        num_samples = payload.get("numSamples", 1)
        interval = payload.get("interval", 0)
        contents = payload.get("contents", True)
        paginate = payload.get("paginate", num_samples)
        if paginate == 0:
            paginate = num_samples

        #TODO - validate the contents dict against the endpoint's schema before starting the stream

        self._exit_flag = threading.Event() # Create a new exit flag for this polling session
        poll_thread = threading.Thread(target=self.repeat_polling, args=(num_samples, interval, contents, paginate))
        poll_thread.start()
        poll_thread.join()
        self._exit_flag = None # Reset exit flag after polling finishes
    

    def repeat_polling(self, 
        num_samples: int, 
        interval: float, 
        contents: Dict[str, Any] | bool,
        paginate: int):
        """
        Repeat the polling function for the given number of samples and interval. It appends the data to the return_data
            list provided to it. (It does this rather than return since threading calls don't support returns.)
        """
        loop_range = itertools.count() if num_samples == 0 else range(num_samples)
        start_perf_counter = time.perf_counter_ns()
        data_list: List[Dict[str, Any]] = []

        if self._exit_flag == None:
            raise ValueError("Exit flag not initialized for polling thread.")

        for _ in loop_range:
            if self._exit_flag.wait(timeout=0.001):
                break

            current_perf_counter_diff = time.perf_counter_ns()-start_perf_counter
            if len(data_list) == 0:
                current_perf_counter_diff = 0

            data = self._poll_function()

            if contents is not True:
                try:
                    data = trim_payload_by_contents(data, contents)
                except PayloadBuildingError as e:
                    self.service.logger.error(f"Error trimming payload: {e.message}")
                    return

            data_list.append({
                "s": current_perf_counter_diff // int(1e9),
                "ns": current_perf_counter_diff % int(1e9),
                "data": data
            })

            # If paginate is set and we've reached the page size, publish the current list and reset it
            if len(data_list) >= paginate > 0:
                self.out_data_endpoint.publish(payload=data_list)
                data_list = []
                start_perf_counter = time.perf_counter_ns()

            time.sleep(interval)
        
        # Publish any remaining data
        if len(data_list) > 0:
            self.out_data_endpoint.publish(payload=data_list)


    def start_stream_handler(self, payload: Dict):
        """
        Handle a stream start request by starting a thread that calls the start stream function with a callback to queue the stream data.
         The start stream function should call the callback with each new piece of data to be published.
        """
        num_samples = payload.get("numSamples", 0)
        contents = payload.get("contents", True)
        paginate = payload.get("paginate", num_samples)
        if paginate == 0:
            paginate = num_samples

        #TODO - validate the contents dict against the endpoint's schema before starting the stream

        self._exit_flag = threading.Event() # Create a new exit flag for this streaming session
        stream_context = StreamContext(num_samples=num_samples, contents=contents, paginate=paginate)
        queue_func = partial(self.queue_stream_data, stream_context=stream_context)
        stream_thread = threading.Thread(target=self._start_stream_function, kwargs={"channel": self, "queue_func": queue_func, "exit_flag": self._exit_flag})
        stream_thread.start()
        stream_thread.join()
        self._exit_flag = None # Reset exit flag after streaming finishes
    

    def queue_stream_data(self, data: Any, stream_context: StreamContext):
        """
        Callback for the stream function.

        Args:
            data: The data to be published, provided by the user code.
            stream_context (StreamContext): The context of the current stream, provided by start_stream_handler via a partial bind.
        """
        stream_context.start_perf_counter = time.perf_counter_ns() # Reset perf counter for more accurate timing of stream data

        if self._exit_flag.wait(timeout=0.001):
            return

        current_perf_counter_diff = time.perf_counter_ns()-stream_context.start_perf_counter
        if len(stream_context.data_list) == 0:
            current_perf_counter_diff = 0

        if stream_context.contents is not True:
            try:
                data = trim_payload_by_contents(data, stream_context.contents)
            except PayloadBuildingError as e:
                self.service.logger.error(f"Error trimming payload: {e.message}")
                return

        stream_context.data_list.append({
            "s": current_perf_counter_diff // int(1e9),
            "ns": current_perf_counter_diff % int(1e9),
            "data": data
        })
        stream_context.samples_processed += 1

        # If paginate is set and we've reached the page size, publish the current list and reset it
        if len(stream_context.data_list) >= stream_context.paginate:
            self.out_data_endpoint.publish(payload=stream_context.data_list)
            stream_context.data_list = []
            stream_context.start_perf_counter = time.perf_counter_ns()
        
        # Publish any remaining data
        if stream_context.samples_processed >= stream_context.num_samples and len(stream_context.data_list) > 0:
            self._exit_flag.set() # Signal the stream to stop if we've processed the requested number of samples
            self.out_data_endpoint.publish(payload=stream_context.data_list)


    def stop_handler(self):
        """
        Stop the channel's polling/streaming.
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


