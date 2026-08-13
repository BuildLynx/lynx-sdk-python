"""
Node class for Lynx. A Node is an extension of an MQTT broker that tracks state of connected services and can forward messages to a parent node.

Generative AI was used in the Creation/Modification of this file.
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import Optional, Dict, Tuple
import logging

# -Lynx Imports-
from lynx_sdk.core.client_component import ClientComponent
from lynx_sdk.messaging.time_source import TimeSource
from lynx_sdk.messaging.endpoint import InEndpoint, OutEndpoint
from lynx_sdk.messaging.mqtt_client import InboundMessage
from lynx_sdk.protocol.component_type import ComponentType
from lynx_sdk.protocol.version import LYNX_VERSION
from lynx_sdk.protocol.schemas import \
    GET_ABOUT_ENDPOINT_ARGS, \
    NODE_SYS_ABOUT_ENDPOINT_ARGS, \
    SYS_NOTICE_ENDPOINT_ARGS, \
    SUBSCRIBE_ABOUT_ENDPOINT_ARGS
from lynx_sdk.protocol.contents import trim_payload_by_contents, PayloadBuildingError
from lynx_sdk.runtime.notice_handler import LoggingNoticeHandler

# -External Imports-



# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class Node(ClientComponent):
    def __init__(self,
        id: str,
        title: str = "",
        description: str = "",
        lynx_version: str = LYNX_VERSION,
        time_source: Optional[TimeSource] = None,
        logger: Optional[logging.Logger] = None,
        parent_node_socket: Optional[Tuple[str, int]] = None,
        publish_logs_as_notices: bool = True):

        super().__init__(
            id=id, 
            component_type=ComponentType.NODE, 
            title=title, 
            description=description, 
            lynx_version=lynx_version,
            time_source=time_source,
            logger=logger,
            track_network_state=True)
        
        self.parent_node_socket: Optional[Tuple[str, int]] = parent_node_socket
        
        self.sys_about_endpoint: OutEndpoint = self.new_out_endpoint(**NODE_SYS_ABOUT_ENDPOINT_ARGS)
        self.get_about_endpoint: InEndpoint = self.new_in_endpoint(
            lambda msg: self.sys_about_endpoint.publish(payload=self.produce_about()),
            **GET_ABOUT_ENDPOINT_ARGS)
        self.sys_notice_endpoint: OutEndpoint = self.new_out_endpoint(**SYS_NOTICE_ENDPOINT_ARGS)
        self.monitor_about_endpoint: InEndpoint = self.new_in_endpoint(
            self.network_state.update_from_about_message,
            **SUBSCRIBE_ABOUT_ENDPOINT_ARGS)

        # all_endpoint_topics_set is not appended in Component._create_endpoint because we don't want Channels to have repeat endpoints
        self.client_endpoint_topics_set.update(set[str](self.endpoints.keys())) 
        
        # -Setup logging with notices-
        if publish_logs_as_notices:
            self.logger.addHandler(LoggingNoticeHandler(endpoint=self.sys_notice_endpoint))

        self.about_cache: Dict = {
            "lynxType": "Node",
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
            "services": {},
            "childNodes": {}
        }
    

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
        Produce a dictionary of information about the node.
        """
        return self.about_cache

        
    def publish_about(self) -> Dict:
        """
        Publish the about information of the node.
        """
        self.sys_about_endpoint.publish(payload=self.produce_about())


# === MAIN LOOP ===


