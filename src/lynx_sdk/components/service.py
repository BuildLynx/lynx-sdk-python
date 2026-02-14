"""
Service 
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import List, Dict, Callable, Any, Optional
from dataclasses import dataclass
from logging import Logger, getLogger
import time

# -Lynx Imports-
from lynx_sdk.components.channel import Channel
from lynx_sdk.utils.structures import LYNX_VERSION
from lynx_sdk.singletons.time_source import TimeSource, instantiate_ideal_time_source
from lynx_sdk.models.endpoint import Endpoint, LynxEndpointDirection, SubEndpoint, PubEndpoint

# -External Imports-
import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes
import orjson


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
        get_about_topic: str = f"{self.id}/?/About"
        sys_about_topic: str = f"{self.id}/@/About"
        self.endpoints: Dict[str, Endpoint] = {
            get_about_topic: SubEndpoint(
                topic=get_about_topic,
                handler=lambda args: self.publish_using_endpoint(self.endpoints[sys_about_topic], self.produce_about()),
                description="Get information about the Service.",
                payload_schema={}),
            sys_about_topic: PubEndpoint(
                topic=sys_about_topic,
                description="Emit information about the Service.",
                payload_schema={}),
        }
        # -Channels-
        self.channels: Dict[str, Channel] = {}
        # -Logger-
        self.logger: Logger = logger or getLogger(self.id)
        # -MQTT Client-
        self.client: mqtt.Client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, 
            client_id=self.id,
            protocol=mqtt.MQTTv5
        )


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
                service=self,
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
                service=self,
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


    def on_connect(self, client:mqtt.Client, userdata:Any, flags:Dict, reason_code:int, properties:Properties):
        """
        Callback for when the client connects to the MQTT broker.
        """
        self.logger.info(f"Connected to MQTT broker with result code {reason_code}")
        self.client.subscribe(f"{self.id}/#")
    

    def publish_using_endpoint(self, endpoint:Endpoint, payload:Dict, qos:Optional[int]=None, retain:Optional[bool]=None):
        """
        Publish a payload using an endpoint.
        """
        #TODO: Add validation of payload
        qos = qos or endpoint.default_qos
        retain = retain or endpoint.default_retain
        publish_properties = Properties(PacketTypes.PUBLISH)
        publish_time = self.time_source.get_time()
        publish_properties.UserProperty = ("time", f"{publish_time['sec']}.{publish_time['nsec']}")
        self.client.publish(
            topic=endpoint.topic,
            payload=orjson.dumps(payload),
            qos=qos,
            retain=retain,
            properties=publish_properties)


    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the service.
        """
        return {
            "type": "service",
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
            "channels": {
                channel.id: channel.produce_about() for channel in self.channels.values()
            }
        }


    def start(self):
        """
        Start the service and MQTT Client.
        """
        for endpoint in self.endpoints.values():
            if endpoint.endpoint_direction == LynxEndpointDirection.SUB:
                self.client.message_callback_add(
                    sub=endpoint.topic, 
                    callback=endpoint.callback)
        for channel in self.channels.values():
            for endpoint in channel.endpoints.values():
                if endpoint.endpoint_direction == LynxEndpointDirection.SUB:
                    self.client.message_callback_add(
                        sub=endpoint.topic,
                        callback=endpoint.callback)

        self.client.on_message = self.no_endpoint_message
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


