"""
A class to represent the current state of the network as known by a ClientComponent.

Generative AI was used in the Creation/Modification of this file.
"""

from typing import Dict, Any, List, Tuple, FrozenSet

from lynx_sdk.messaging.mqtt_client import InboundMessage
from lynx_sdk.protocol.dicts import deep_merge
from lynx_sdk.protocol.component_type import ComponentType


# Top-level keys allowed on a partial About (mutable fields only).
PARTIAL_ABOUT_KEYS: FrozenSet[str] = frozenset({"status", "config"})


class NetworkState():

    def __init__(self):
        self.state: Dict[str, Any] = self.generate_empty_node_state()

    def generate_empty_node_state(self) -> Dict[str, Any]:
        """
        Generate an empty node state.
        """
        return {"services": {}, "childNodes": {}}

    def recursively_set_path(
        self,
        path: List[Tuple[str, ComponentType]],
        state_scope: Dict[str, Any],
        final_payload: Dict[str, Any]):
        """
        Recursively checks to see if the path to insert the About payload into the state already exists, and creates
        it if it doesn't. Then it inserts the final payload into the state.
        Args:
            path: A list of tuples, each containing an id and a component type.
            state_scope: The scope of the state to set the path in. The state scope is a dictionary of dictionaries,
            final_payload: The payload to insert into the state.

        Returns:
            True if any part of the path was created, False otherwise.
        """
        component_id = path[0][0]
        component_type = path[0][1]
        if component_type == ComponentType.SERVICE:
            if component_id not in state_scope["services"]:
                state_scope["services"][component_id] = final_payload
            state_scope["services"][component_id] = deep_merge(state_scope["services"][component_id], final_payload, make_copy=False)
        elif component_type == ComponentType.NODE:
            if component_id not in state_scope["childNodes"]:
                state_scope["childNodes"][component_id] = self.generate_empty_node_state()
            if len(path) == 1:
                state_scope["childNodes"][component_id] = deep_merge(state_scope["childNodes"][component_id], final_payload, make_copy=False)
            else:
                self.recursively_set_path(path[1:], state_scope["childNodes"][component_id], final_payload)
        else:
            raise ValueError(f"Invalid component type: {component_type}")

    def _classify_about(self, payload: Dict[str, Any]) -> str:
        """
        Place an About payload as Service or Node.

        lynxType is authoritative. A Node About contains both services and
        childNodes, so key sniffing is only used when lynxType is absent.
        """
        lynx_type = payload.get("lynxType")
        if lynx_type in (ComponentType.SERVICE.value, ComponentType.NODE.value):
            return lynx_type
        if "channels" in payload:
            return ComponentType.SERVICE.value
        if "childNodes" in payload:
            return ComponentType.NODE.value
        raise ValueError(f"Invalid Lynx type: {lynx_type}. Payload: {payload}")

    def update_from_about_message(self, msg: InboundMessage):
        """
        Update the network state from an about message.
        Args:
            msg: The inbound message containing the about information.
        """
        # Start to make tuple list of component path up to the last ID
        component_path_list :List[str] = msg.topic.split("/")[:-2]
        component_path_tuple_list :List[Tuple[str, ComponentType]] = \
            [(component_id, ComponentType.NODE) for component_id in component_path_list[:-1]]

        # Partial About: payload contains only mutable fields (e.g. LWT {"status":{"connected":false}}).
        # Merge onto the existing Service or Node entry; leave channel status.command untouched.
        if msg.payload.keys() <= PARTIAL_ABOUT_KEYS:
            if msg.payload and len(component_path_list) >= 1:
                component_id = component_path_list[-1]
                entry = self.state.get("services", {}).get(component_id)
                if entry is None:
                    entry = self.state.get("childNodes", {}).get(component_id)
                if entry is not None:
                    deep_merge(entry, msg.payload, make_copy=False)
            return
        lynx_type = self._classify_about(msg.payload)
        component_path_tuple_list.append((component_path_list[-1], ComponentType(lynx_type)))
        self.recursively_set_path(component_path_tuple_list, self.state, msg.payload)
