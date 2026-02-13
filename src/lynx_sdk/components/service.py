"""
Service 
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import List, Dict, Callable, Any
from dataclasses import dataclass
from logging import Logger, getLogger
import time

# -Lynx Imports-
from lynx_sdk.components.channel import Channel
from lynx_sdk.utils.structures import LYNX_VERSION
from lynx_sdk.singletons.time_source import TimeSource, instantiate_ideal_time_source
from lynx_sdk.models.endpoint import Endpoint, LynxEndpointDirection, SubEndpoint

# -External Imports-
import paho.mqtt.client as mqtt


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

@dataclass
class Service():
    def __init__(self,
        id: str,
        title: str = "",
        description: str = "",
        lynx_version: str = LYNX_VERSION,
        time_source: TimeSource = None,
        logger: Logger = None):
        """
        Initialize a Lynx Service object.
        """

        # -Docs-
        self.id: str = id
        self.title: str = title
        self.description: str = description
        self.lynx_version: str = lynx_version
        # -Time Source-
        self.time_source: TimeSource = time_source or instantiate_ideal_time_source()
        # -Endpoints-
        self.endpoints: Dict[str, Endpoint] = {
            "?/About": SubEndpoint(
                topic="?/About",
                handler=lambda args: print("About:", args),
                description="Get information about the service.",
                payload_schema={}),
        }
        # -Channels-
        self.channels: Dict[str, Channel] = {}
        # -Logger-
        self.logger: Logger = logger or getLogger(self.id)
        # -MQTT Client-
        self.client: mqtt.Client = mqtt.Client()


    @classmethod
    def from_dict(cls, service_dict: Dict, create_channels: bool=False):
        """
        Initialize a Lynx Service object from a dictionary.
        """
        if create_channels:
            channels = {{id, Channel.from_dict(channel_dict)} for id, channel_dict in service_dict["channels"].items()}
        else:
            channels = {}

        return cls(
            id=service_dict["id"],
            title=service_dict["title"],
            description=service_dict["description"],
            lynx_version=service_dict["lynx_version"],
            time_source=service_dict["time_source"],
            endpoints={{id, Endpoint.from_dict(endpoint_dict)} for id, endpoint_dict in service_dict["endpoints"].items()},
            channels=channels
        )


    def add_channel(self, channel: Channel):
        """
        Add a channel to the service.
        """
        self.channels[channel.id] = channel


    def new_poll_channel(
        self,
        id: str,
        title: str = "",
        description: str = "",
        output_data_schema: Dict = None,
        time_source: TimeSource = None):
        """
        Create a new poll channel for the service.
        """

        if time_source is None:
            time_source = self.time_source
        
        def decorator(poll_function: Callable):
            new_channel = Channel(
                id=id,
                client=self.client,
                title=title,
                description=description,
                poll_function=poll_function,
                start_stream_function=None,
                output_data_schema=output_data_schema,
                lynx_version=self.lynx_version,
                time_source=time_source)
            self.channels[id] = new_channel
            return new_channel
        return decorator
    

    def new_stream_channel(
        self,
        id: str,
        title: str = "",
        description: str = "",
        output_data_schema: Dict = None,
        time_source: TimeSource = None):
        """
        Create a new stream channel for the service.
        """

        if time_source is None:
            time_source = self.time_source
        
        def decorator(start_stream_function: Callable):
            new_channel = Channel(
                id=id,
                client=self.client,
                title=title,
                description=description,
                poll_function=None,
                start_stream_function=start_stream_function,
                output_data_schema=output_data_schema,
                lynx_version=self.lynx_version,
                time_source=time_source)
            self.channels[id] = new_channel
            return new_channel
        return decorator
    

    def add_endpoint(self, endpoint: Endpoint):
        """
        Add an endpoint to the service.
        """
        self.endpoints[endpoint.id] = endpoint
    

    def no_endpoint_message(self, client, userdata, message):
        """
        Emit a notice that the service received a message on an endpoint that is not configured.
        """
        print(f"Received message on topic {message.topic} but no endpoint is configured to handle it.")
    

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict, rc: int):
        """
        Callback for when the client connects to the MQTT broker.
        """
        self.logger.info(f"Connected to MQTT broker with result code {rc}")
        self.client.subscribe(f"{self.id}/#")


    def start(self):
        """
        Start the service and MQTT Client.
        """
        for (endpoint_id, endpoint) in self.endpoints.items():
            if endpoint.endpoint_direction == LynxEndpointDirection.SUB:
                self.client.message_callback_add(
                    sub=f"{self.id}/{endpoint.topic}", 
                    callback=endpoint.callback)
        for (channel_id, channel) in self.channels.items():
            for (endpoint_id, endpoint) in channel.endpoints.items():
                if endpoint.endpoint_direction == LynxEndpointDirection.SUB:
                    self.client.message_callback_add(
                        sub=f"{self.id}/{channel.id}/{endpoint.topic}",
                        callback=endpoint.callback)
                    print(f"{self.id}/{channel.id}/{endpoint.topic}")

        self.client.on_message = self.no_endpoint_message
        # self.client.message_callback_add("#", lambda client, userdata, message: self.logger.info(f"Received message on topic {message.topic}"))
        self.client.on_connect = self.on_connect
        try:
            self.client.connect(host="localhost", port=1883, keepalive=60)
        except ConnectionRefusedError as e:
            self.logger.error(f"Failed to connect to MQTT broker, is the broker running?")
            return
        self.client.loop_start()
        while True:
            time.sleep(1)

        
# === MAIN LOOP ===


