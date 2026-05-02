"""
Node class for Lynx. A Node is an extension of an MQTT broker that tracks state of connected services and can forward messages to a parent node.
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import Optional, Dict, Tuple
import logging

# -Lynx Imports-
from lynx_sdk.components.client_component import ClientComponent
from lynx_sdk.components.component import ComponentType
from lynx_sdk.utils.structures import LYNX_VERSION
from lynx_sdk.models.time_source import TimeSource
from lynx_sdk.models.endpoint import SubEndpoint, PubEndpoint
from lynx_sdk.models.endpoint_args import \
    GET_ABOUT_ENDPOINT_ARGS, \
    NODE_SYS_ABOUT_ENDPOINT_ARGS, \
    SYS_NOTICE_ENDPOINT_ARGS, \
    NODE_MONITOR_ABOUT_ENDPOINT_ARGS
from lynx_sdk.models.notice import LoggingNoticeHandler
from lynx_sdk.utils.datastructures import deep_merge
from lynx_sdk.utils.json_tools import trim_payload_by_contents, PayloadBuildingError

# -External Imports-



# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class Node(ClientComponent):
    def __init__(self,
        id: str,
        broker_socket: Tuple[str, int],
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
            broker_socket=broker_socket)
        
        self.broker_socket: Tuple[str, int] = broker_socket
        self.parent_node_socket: Optional[Tuple[str, int]] = parent_node_socket
        
        self.sys_about_endpoint: PubEndpoint = self.new_pub_endpoint(NODE_SYS_ABOUT_ENDPOINT_ARGS)
        self.get_about_endpoint: SubEndpoint = self.new_sub_endpoint(GET_ABOUT_ENDPOINT_ARGS,
            lambda args: self.sys_about_endpoint.publish(payload=self.produce_about()))
        self.sys_notice_endpoint: PubEndpoint = self.new_pub_endpoint(SYS_NOTICE_ENDPOINT_ARGS)
        self.monitor_about_endpoint: SubEndpoint = self.new_sub_endpoint(NODE_MONITOR_ABOUT_ENDPOINT_ARGS, self.handle_monitor_about_endpoint)

        # all_endpoint_topics_set is not appended in Component._create_endpoint because we don't want Channels to have repeat endpoints
        self.client_endpoint_topics_set.update(set[str](self.endpoints.keys())) 
        
        # -Setup logging with notices-
        if publish_logs_as_notices:
            self.logger.addHandler(LoggingNoticeHandler(endpoint=self.sys_notice_endpoint))

        self.about_cache: Dict = {
            "lynxType": "node",
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
            "child_nodes": {}
        }
    
    
    def handle_monitor_about_endpoint(self, payload: Dict):
        """
        Handle incoming About messages from child nodes and services.
        """
        if payload["lynxType"] == "service":
            aligned_payload = {
                "services": {
                    payload["docs"]["id"]: payload
                }
            }
            self.about_cache = deep_merge(self.about_cache, aligned_payload)
        elif payload["lynxType"] == "node":
            aligned_payload = {
                "child_nodes": {
                    payload["docs"]["id"]: payload
                }
            }
            self.about_cache = deep_merge(self.about_cache, aligned_payload)
        elif payload["lynxType"] == "channel":
            self.logger.warning(f"Received channel about message from {payload['id']}, which is not supported by Node.")
        else:
            self.logger.warning(f"Received unknown lynxType in about message. {payload['id']}: {payload['lynxType']}")
    

    def about_handler(self, payload: Dict):
        """
        Handle incoming About messages from the service.
        """
        contents = payload.get("contents", True)
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
    

    def get_client_component(self) -> ClientComponent:
        """
        Get the Node (returns self since this IS the Node).
        """
        return self

# === MAIN LOOP ===


