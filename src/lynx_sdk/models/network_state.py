# Generative AI was used in the Creation/Modification of this file
"""
A class to represent the current state of the network as known by a ClientComponent.
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import Dict, Any, List, Tuple, FrozenSet

# -Lynx Imports-
from lynx_sdk.utils.mqtt_client import InboundMessage
from lynx_sdk.utils.datastructures import deep_merge
from lynx_sdk.components.component import ComponentType

# -External Imports-



# === CONSTANTS ===

# Top-level keys allowed on a partial About (mutable fields only).
PARTIAL_ABOUT_KEYS: FrozenSet[str] = frozenset({"status", "config"})


# === GLOBALS VARIABLES ===



# === FUNCTIONS ===

# def initial_state():
#     """
#     Create a recursive defaultdict of initial_state for the network state.
#     This allows setting values at any depth like initial_state()["a"]["b"]["c"] = "d", even if none of the intermediate keys exist.
#     Example here: https://stackoverflow.com/questions/19189274/nested-defaultdict-of-defaultdict
#     """
#     return defaultdict(initial_state)



#  === CLASSES ===

class NetworkState():

    def __init__(self):
        self.state: Dict[str, Any] = self.generate_empty_node_state()
    

    def generate_empty_node_state(self) -> Dict[str, Any]:
        """
        Generate an empty node state.
        """
        return {"services": {}, "childNodes": {}}


    def recursively_set_path(self, 
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
        id = path[0][0]
        component_type = path[0][1]
        if component_type == ComponentType.SERVICE:
            if id not in state_scope["services"]:
                state_scope["services"][id] = final_payload
            state_scope["services"][id] = deep_merge(state_scope["services"][id], final_payload, make_copy=False)
        elif component_type == ComponentType.NODE:
            if id not in state_scope["childNodes"]:
                state_scope["childNodes"][id] = self.generate_empty_node_state()
            if len(path) == 1:
                state_scope["childNodes"][id] = deep_merge(state_scope["childNodes"][id], final_payload, make_copy=False)
            else:
                self.recursively_set_path(path[1:], state_scope["childNodes"][id], final_payload)
        else:
            raise ValueError(f"Invalid component type: {component_type}")
    
    
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
        # Merge onto the service entry only; leave channel status.command untouched.
        if msg.payload.keys() <= PARTIAL_ABOUT_KEYS:
            if msg.payload and len(component_path_list) >= 1:
                service_id = component_path_list[-1]
                service_entry = self.state.get("services", {}).get(service_id)
                if service_entry is not None:
                    deep_merge(service_entry, msg.payload, make_copy=False)
            return
        lynx_type = msg.payload.get("lynxType", None)
        if "channels" in msg.payload or "services" in msg.payload:
            lynx_type = "Service"
        elif "childNodes" in msg.payload:
            lynx_type = "Node"
        else:
            raise ValueError(f"Invalid Lynx type: {lynx_type}. Payload: {msg.payload}")
        component_path_tuple_list.append((component_path_list[-1], ComponentType(lynx_type)))
        self.recursively_set_path(component_path_tuple_list, self.state, msg.payload)



# === MAIN LOOP ===
