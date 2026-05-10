"""
Service class for Lynx. A Service is the encapsulation of a single application or service, it contains Channels, 
a Time Source, an MQTT Client, and has its own Endpoints.
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import Dict, Callable, Optional, Tuple
import logging

# -Lynx Imports-
from lynx_sdk.components.client_component import ClientComponent
from lynx_sdk.components.component import ComponentType
from lynx_sdk.components.channel import Channel
from lynx_sdk.models.time_source import TimeSource
from lynx_sdk.models.endpoint import SubEndpoint, PubEndpoint
from lynx_sdk.models.endpoint_args import \
    GET_ABOUT_ENDPOINT_ARGS, \
    SERVICE_SYS_ABOUT_ENDPOINT_ARGS, \
    SYS_NOTICE_ENDPOINT_ARGS, \
    SUBSCRIBE_ABOUT_ENDPOINT_ARGS
from lynx_sdk.models.network_state import NetworkState
from lynx_sdk.models.notice import LoggingNoticeHandler
from lynx_sdk.utils.mqtt_client import InboundMessage
from lynx_sdk.utils.json_tools import trim_payload_by_contents, PayloadBuildingError
from lynx_sdk.utils.structures import LYNX_VERSION

# -External Imports-


# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class Service(ClientComponent):
    def __init__(self,
        id: str,
        title: str = "",
        description: str = "",
        lynx_version: str = LYNX_VERSION,
        time_source: Optional[TimeSource] = None,
        logger: Optional[logging.Logger] = None,
        publish_logs_as_notices: bool = True,
        track_network_state: bool = False):
        """
        Initialize a Lynx Service object.
        
        Args:
            id: Unique identifier for this service
            title: Human-readable title
            description: Human-readable description
            lynx_version: Lynx protocol version
            time_source: Time source for timestamps (defaults to ideal source for platform)
            logger: Logger for this service (defaults to logger named after id)
            publish_logs_as_notices: Whether to publish log messages as notices to MQTT
            track_network_state: Whether to track the network state for this service.
        """

        # Initialize Component base class
        super().__init__(
            id=id,
            component_type=ComponentType.SERVICE,
            title=title,
            description=description,
            lynx_version=lynx_version,
            time_source=time_source,
            logger=logger,
            track_network_state=track_network_state
        )
        
        # -Service-specific initialization-
        # -Channels-
        self.channels: Dict[str, Channel] = {}
        
        # -Endpoints-
        self.sys_about_endpoint: PubEndpoint = self.new_pub_endpoint(**SERVICE_SYS_ABOUT_ENDPOINT_ARGS)
        self.get_about_endpoint: SubEndpoint = self.new_sub_endpoint(self.about_handler, **GET_ABOUT_ENDPOINT_ARGS)
        self.sys_notice_endpoint: PubEndpoint = self.new_pub_endpoint(**SYS_NOTICE_ENDPOINT_ARGS)
        # all_endpoint_topics_set is not appended in Component._create_endpoint because we don't want Channels to have repeat endpoints
        self.client_endpoint_topics_set.update(set[str](self.endpoints.keys())) 
        
        # -Setup logging with notices-
        if publish_logs_as_notices:
            self.logger.addHandler(LoggingNoticeHandler(endpoint=self.sys_notice_endpoint))

        if track_network_state:
            self.new_sub_endpoint(self.network_state.update_from_about_message, **SUBSCRIBE_ABOUT_ENDPOINT_ARGS)


    def get_client_component(self) -> ClientComponent:
        """
        Get the Service (returns self since this IS the Service).
        """
        return self
    
    
    def new_channel(
        self,
        id: str,
        title: str = "",
        description: str = "",
        output_data_schema: Optional[Dict] = None):
        """
        Create a new channel with a poll callback for the service.
        """
        def decorator(sample_function: Callable):
            new_channel = Channel(
                id=id,
                service=self,
                title=title,
                description=description,
                sample_function=sample_function,
                output_data_schema=output_data_schema,
                lynx_version=self.lynx_version)
            self.add_channel(new_channel)
            return new_channel
        return decorator
    

    def add_channel(self, channel: Channel):
        """
        Add a channel to the service.
        """
        if channel.id in self.channels:
            raise ValueError(f"Channel with id {channel.id} already exists in service {self.id}")
        self.channels[channel.id] = channel
        self.client_endpoint_topics_set.update(set[str](channel.endpoints.keys()))


    def about_handler(self, msg: InboundMessage):
        """
        Handle incoming About messages from the service.
        """
        payload = msg.payload
        contents = payload.get("contents", True)
        outgoing_payload = self.produce_about()
        if contents is not True:
            try:
                outgoing_payload = trim_payload_by_contents(self.produce_about(), contents)
            except PayloadBuildingError as e:
                self.logger.error(f"Error trimming payload: {e.message}")
                return
        self.sys_about_endpoint.publish(payload=outgoing_payload)


    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the service.
        """
        return {
            "lynxType": "Service",
            "docs": {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "lynx_version": self.lynx_version,
                "time_source": self.time_source.time_source_type.value,
            },
            "config": {},
            "status": self.get_status_dict(),
            "endpoints": {
                endpoint.topic: endpoint.produce_about() for endpoint in self.endpoints.values()
            },
            "channels": {
                channel.id: channel.produce_about() for channel in self.channels.values()
            }
        }
    

    def publish_about(self):
        """
        Publish the about information to the MQTT broker.
        """
        self.sys_about_endpoint.publish(payload=self.produce_about(), qos=1, retain=True)
    

# === MAIN LOOP ===


