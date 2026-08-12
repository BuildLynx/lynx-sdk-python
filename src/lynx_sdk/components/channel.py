"""
Channel class for Lynx. A Channel is the encapsulation of a single input and/or output data stream.
"""



# === IMPORTS ===

# -stdlib Imports-
from __future__ import annotations
from typing import Callable, Dict, Any, Optional, TYPE_CHECKING
from copy import deepcopy
import threading

# -Lynx Imports-
from lynx_sdk.components.component import Component, ComponentType
from lynx_sdk.components.client_component import ClientComponent
from lynx_sdk.models.endpoint import OutEndpoint
from lynx_sdk.models.endpoint_args import \
    CHANNEL_CMD_POLL_ENDPOINT_ARGS, \
    CHANNEL_CMD_STREAM_ENDPOINT_ARGS, \
    CHANNEL_CMD_STOP_ENDPOINT_ARGS, \
    CHANNEL_OUT_DATA_ENDPOINT_ARGS
from lynx_sdk.components.stream_batcher import (
    StreamBatcher,
    DEFAULT_NUM_SAMPLES,
    DEFAULT_SAMPLE_INTERVAL,
    resolve_batch_limits,
)
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

        self._status = {"command": None}
        
        # -Channel-specific initialization-
        self.service: Service = service
        self._sample_function: Callable[[InboundMessage], Any] = sample_function
        self._exit_flag: threading.Event = threading.Event() # Flag to signal polling/streaming thread to exit
        self._stream_batcher: Optional[StreamBatcher] = None
        self._stream_thread: Optional[threading.Thread] = None

        self.cmd_poll_endpoint = self.new_in_endpoint(self.poll_handler, **CHANNEL_CMD_POLL_ENDPOINT_ARGS)
        self.cmd_stream_endpoint = self.new_in_endpoint(self.start_stream_handler, **CHANNEL_CMD_STREAM_ENDPOINT_ARGS)
        self.cmd_stop_endpoint = self.new_in_endpoint(self.stop_handler, **CHANNEL_CMD_STOP_ENDPOINT_ARGS)

        if output_data_schema is not None:
            channel_out_data_schema = deepcopy(CHANNEL_OUT_DATA_ENDPOINT_ARGS)
            channel_out_data_schema["payload_schema"]["items"]["properties"]["data"]["properties"] = output_data_schema
            self.out_data_endpoint: OutEndpoint = self.new_out_endpoint(**channel_out_data_schema)

        self.config: Dict[str, Any] = config
        if self.config.get("streamOnStartup", False):
            self.start_stream_handler(msg=InboundMessage(topic="", payload={"contents": True}))


    def get_client_component(self) -> ClientComponent:
        """
        Get the Service that owns resources (MQTT client, time_source, logger).
        """
        return self.service


    def poll_handler(self, msg: InboundMessage):
        """
        Handle a poll request.
        """
        contents = msg.payload.get("contents", True)

        for data in self._sample_function(request=msg, continue_sampling=lambda **kwargs: True): # Assume true because we only sample once
            if contents is not True:
                try:
                    data = trim_payload_by_contents(data, contents)
                except PayloadBuildingError as e:
                    self.service.logger.error(f"Error trimming payload: {e.message}")
                    return
            payload = [{"s": 0, "ns": 0, "data": data}]

            self.out_data_endpoint.publish(payload=payload)
            break
        


    def start_stream_handler(self, msg: InboundMessage):
        """
        Handle a stream start request. Sampling runs on a thread; batch flushes
        (including empty keepalives and Stop) are independent of that thread.
        """
        active = self._status.get("command")
        thread_busy = self._stream_thread is not None and self._stream_thread.is_alive()
        if (isinstance(active, dict) and active.get("command") == "Stream") or thread_busy:
            self.service.logger.warning(f"Channel '{self.id}' is already streaming, ignoring stream start request.")
            return
        
        payload = msg.payload
        contents = payload.get("contents", True)
        num_samples = int(payload.get("numSamples", DEFAULT_NUM_SAMPLES))
        max_interval, max_samples = resolve_batch_limits(payload)

        #TODO - validate the contents dict against the endpoint's schema before starting the stream

        self._exit_flag.clear()
        self.set_status(command={"command": "Stream", "payload": msg.payload})
        batcher = StreamBatcher(
            contents=contents,
            max_interval=max_interval,
            max_samples=max_samples,
            num_samples=num_samples,
            publish=self.out_data_endpoint.publish,
            logger=self.service.logger,
            on_ended=self._on_stream_ended)
        batcher.start()
        self._stream_batcher = batcher
        stream_thread = threading.Thread(
            target=self._stream_handler,
            kwargs={"request": msg, "batcher": batcher},
            daemon=True)
        self._stream_thread = stream_thread
        stream_thread.start()

    
    def _on_stream_ended(self):
        """
        Called once when the batcher ends the stream (Stop, numSamples, or generator finish).
        """
        self._exit_flag.set()
        self.set_status(command=None)

    
    def _stream_handler(self, request: InboundMessage, batcher: StreamBatcher):
        """
        Run the sample function. Each yield is add_sample; publishing is the batcher's job.
        """
        def continue_sampling(default_interval: float = DEFAULT_SAMPLE_INTERVAL):
            """
            Determine if the sampling should continue.
            Args:
                default_interval: Sleep used when the Stream payload omits sampleInterval.
            Returns:
                True if the sampling should continue, False otherwise.
            """
            interval = request.payload.get("sampleInterval", default_interval)
            return not self._exit_flag.wait(timeout=interval)

        try:
            for data in self._sample_function(request=request, continue_sampling=continue_sampling):
                if self._exit_flag.is_set():
                    break
                if not batcher.add_sample(data):
                    break
        finally:
            batcher.end_stream()


    def stop_handler(self, msg: InboundMessage):
        """
        Stop the channel's polling/streaming. Flushes immediately, even if the
        sample function is blocked.
        """
        self._exit_flag.set()
        if self._stream_batcher is not None:
            self._stream_batcher.end_stream()


    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the channel.
        """
        return {
            "lynxType": "Channel",
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
        command: Optional[Dict[str, Any]] = None,
        about_endpoint: Optional[OutEndpoint] = None) -> Dict[str, Any]:
        """
        Set the status of the channel. Pass command=None when idle; an object when busy.
        """
        if about_endpoint is None:
            about_endpoint = self.service.sys_about_endpoint
        return super().set_status(about_endpoint=about_endpoint, command=command)
