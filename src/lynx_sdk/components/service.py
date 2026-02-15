"""
Service class for Lynx. A Service is the encapsulation of a single application or service, it contains Channels, 
a Time Source, an MQTT Client, and has its own Endpoints.
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import List, Dict, Callable, Any, Optional
from dataclasses import dataclass
from logging import Logger, getLogger
import time

# -Lynx Imports-
from lynx_sdk.components.component import Component
from lynx_sdk.components.channel import Channel
from lynx_sdk.utils.structures import LYNX_VERSION, ComponentType
from lynx_sdk.utils.mqtt_client import MqttClient
from lynx_sdk.singletons.time_source import TimeSource, instantiate_ideal_time_source
from lynx_sdk.models.endpoint import Endpoint, LynxEndpointDirection, SubEndpoint, PubEndpoint
from lynx_sdk.models.notice import LoggingNoticeHandler

# -External Imports-
from paho.mqtt.properties import Properties


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class ServiceStatus():
    def __init__(self):
        self.action: str = ""
        


class Service(Component):
    def __init__(self,
        id: str,
        title: str = "",
        description: str = "",
        lynx_version: str = LYNX_VERSION,
        time_source: Optional[TimeSource] = None,
        logger: Optional[Logger] = None,
        emit_logs_as_notices: bool = True):
        """
        Initialize a Lynx Service object.
        
        Args:
            id: Unique identifier for this service
            title: Human-readable title
            description: Human-readable description
            lynx_version: Lynx protocol version
            time_source: Time source for timestamps (defaults to ideal source for platform)
            logger: Logger for this service (defaults to logger named after id)
            emit_logs_as_notices: Whether to publish log messages as notices to MQTT
        """

        if time_source is None:
            time_source = instantiate_ideal_time_source()
        if logger is None:
            logger = getLogger(id)

        # Initialize Component base class
        super().__init__(
            id=id,
            component_type=ComponentType.SERVICE,
            title=title,
            description=description,
            lynx_version=lynx_version,
            time_source=time_source,
            logger=logger,
            emit_logs_as_notices=emit_logs_as_notices
        )
        
        # -Service-specific initialization-
        # -Channels-
        self.channels: Dict[str, Channel] = {}
        
        # -MQTT Client-
        self.client: MqttClient = MqttClient(
            client_id=self.id,
            time_source=self.time_source
        )
        
        # -Endpoints-
        self.get_about_endpoint: SubEndpoint = SubEndpoint(
            topic=f"{self.id}/?/About",
            description="Get information about the Service.",
            handler=lambda args: self.endpoints[self.sys_about_endpoint.topic].publish(payload=self.produce_about()),
            mqtt_client=self.client,
            time_source=self.time_source,
            logger=self.logger,
            payload_schema={})
        self.endpoints[self.get_about_endpoint.topic] = self.get_about_endpoint

        self.sys_about_endpoint: PubEndpoint = PubEndpoint(
            topic=f"{self.id}/@/About",
            description="Emit information about the Service.",
            mqtt_client=self.client,
            time_source=self.time_source,
            logger=self.logger,
            payload_schema={},
            default_qos=1,
            default_retain=True)
        self.endpoints[self.sys_about_endpoint.topic] = self.sys_about_endpoint

        self.sys_notice_endpoint: PubEndpoint = PubEndpoint(
            topic=f"{self.id}/@/Notice",
            description="Emit a notice about the Service.",
            mqtt_client=self.client,
            time_source=self.time_source,
            logger=self.logger,
            payload_schema={},
            default_qos=1,
            default_retain=False)
        self.endpoints[self.sys_notice_endpoint.topic] = self.sys_notice_endpoint
        
        # -Setup logging with notices-
        if emit_logs_as_notices:
            self.logger.addHandler(LoggingNoticeHandler(self.sys_notice_endpoint))


    def new_poll_channel(
        self,
        id: str,
        title: str = "",
        description: str = "",
        output_data_schema: Optional[Dict] = None,
        time_source: Optional[TimeSource] = None):
        """
        Create a new channel with a poll callback for the service.
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
        output_data_schema: Optional[Dict] = None,
        time_source: Optional[TimeSource] = None):
        """
        Create a new channel with a start stream callback for the service.
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
    


    def no_endpoint_message(self, client, userdata, message):
        """
        Emit a notice that the service received a message on an endpoint that is not configured.
        """
        self.logger.info(f"Received message on topic {message.topic} but no endpoint is configured to handle it.")


    def on_connect(self, client, userdata: Any, flags: Dict, reason_code: int, properties: Properties):
        """
        Callback for when the client connects to the MQTT broker.
        """
        self.logger.info(f"Connected to MQTT broker with result code {reason_code}")
        self.client.subscribe(f"{self.id}/#")


    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the service.
        Extends the base Component.produce_about() with service-specific channels.
        """
        about = super().produce_about()
        about["channels"] = {
            channel.id: channel.produce_about() for channel in self.channels.values()
        }
        return about


    def start(self):
        """
        Start the service and MQTT Client.
        """
        
        # Set default callbacks
        self.client.set_on_message(self.no_endpoint_message)
        self.client.set_on_connect(self.on_connect)
        
        # Connect to broker
        try:
            self.client.connect(host="localhost", port=1883, keepalive=60)
        except ConnectionRefusedError as e:
            self.logger.error(f"Failed to connect to MQTT broker, is the broker running?")
            return
        
        # Start network loop
        self.client.loop_start()
        
        # Keep service running
        while True:
            time.sleep(1)

        
# === MAIN LOOP ===


