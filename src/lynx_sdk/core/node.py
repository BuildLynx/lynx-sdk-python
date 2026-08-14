"""
Node class for Lynx. A Node is an extension of an MQTT broker that tracks state of connected services and can forward messages to a parent node.

Generative AI was used in the Creation/Modification of this file.
"""

from typing import Dict, Optional, Tuple
import logging

from lynx_sdk.core.client_component import ClientComponent
from lynx_sdk.messaging.time_source import TimeSource
from lynx_sdk.protocol.component_type import ComponentType
from lynx_sdk.protocol.schemas import NODE_SYS_ABOUT_ENDPOINT_ARGS
from lynx_sdk.protocol.version import LYNX_VERSION


class Node(ClientComponent):
    def __init__(
        self,
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
            sys_about_endpoint_args=NODE_SYS_ABOUT_ENDPOINT_ARGS,
            time_source=time_source,
            logger=logger,
            track_network_state=True,
            publish_logs_as_notices=publish_logs_as_notices)

        self.parent_node_socket: Optional[Tuple[str, int]] = parent_node_socket

    def produce_about(self) -> Dict:
        """
        Produce a dictionary of information about the node.
        """
        assert self.network_state is not None
        topology = self.network_state.state
        return {
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
            "services": topology.get("services", {}),
            "childNodes": topology.get("childNodes", {}),
        }
