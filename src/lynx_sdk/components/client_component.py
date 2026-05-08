"""
Client Component base class for Lynx. A Client Component is a component that has its own MQTT client (like Service or Node).
"""



# === IMPORTS ===

# -stdlib Imports-
import logging
from typing import Dict, Any, abstractmethod, Optional, Tuple
import time
import sys

# -Lynx Imports-
from lynx_sdk.components.component import Component, ComponentType
from lynx_sdk.utils.mqtt_client import MqttClient
from lynx_sdk.models.time_source import TimeSource, instantiate_ideal_time_source
from lynx_sdk.models.network_state import NetworkState

# -External Imports-
import paho.mqtt.client as mqtt



# === CONSTANTS ===

CONNECT_RETRY_INTERVAL: int = 5



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

class ClientComponent(Component):
    def __init__(self,
        id: str,
        broker_socket: Tuple[str, int],
        component_type: ComponentType,
        title: str,
        description: str,
        lynx_version: str,
        time_source: Optional[TimeSource] = None,
        logger: Optional[logging.Logger] = None,
        track_network_state: bool = False):
        """
        Initialize a Lynx Client Component.
        Args:
            id: The unique identifier for this component.
            broker_socket: The tuple of (host, port) for the MQTT broker.
            component_type: The type of component this is.
            title: The human-readable title of this component.
            description: The human-readable description of this component.
            lynx_version: The Lynx protocol version this component is using.
            time_source: The time source to use for this component.
            logger: The logger to use for this component.
            track_network_state: Whether to track the network state for this component.
        """
        super().__init__(
            id=id, 
            component_type=component_type, 
            title=title, 
            description=description, 
            lynx_version=lynx_version)
        
        self.broker_socket: Tuple[str, int] = broker_socket
        self.time_source: TimeSource = time_source or instantiate_ideal_time_source()
        
        if logger is None:
            self.logger: logging.Logger = logging.getLogger(id)
            self.logger.setLevel(level=logging.DEBUG)
            stream_handler = logging.StreamHandler(stream=sys.stdout)
            stream_handler.setLevel(level=logging.DEBUG)
            self.logger.addHandler(stream_handler)
            self.logger.propagate = False
        else:
            self.logger = logger

        self.client_endpoint_topics_set: set[str] = set[str]()
        self.mqtt_client: MqttClient = MqttClient(
            client_id=id,
            time_source=self.time_source
        )

        self.network_state: Optional[NetworkState] = NetworkState() if track_network_state else None


    @abstractmethod
    def publish_about(self) -> Dict:
        """
        Publish the about information to the MQTT broker.
        """
        pass
    
    
    def no_endpoint_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage):
        """
        Emit a notice that the service received a message on an endpoint that is not configured.
        """
        if message.topic in self.client_endpoint_topics_set:
            return # This prevents infinite loop of service responding to its own messages
        if not message.topic.startswith(f"{self.id}/"):
            return # If the message is not for this component, ignore it
        self.logger.warning(f"Received message on topic \"{message.topic}\" but no endpoint is configured to handle it.")


    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict, reason_code: int, properties: mqtt.Properties):
        """
        Callback for when the client connects to the MQTT broker.
        """
        try:
            self.logger.debug(f"Connected to MQTT broker with result code {reason_code}")
            subscribe_topic_filter = f"{self.id}/#"
            if any(not topic.startswith(f"{self.id}/") for topic in self.client_endpoint_topics_set):
                subscribe_topic_filter = "#"
            self.mqtt_client.subscribe(subscribe_topic_filter)
            
            self.publish_about()
        except Exception as e:
            self.logger.error(f"Exception in on_connect: {e}", exc_info=True)
            raise
    
    
    def on_disconnect(self, client: mqtt.Client, userdata: Any, disconnect_flags: Dict, reason_code: int, properties: mqtt.Properties):
        """
        Callback for when the client disconnects from the MQTT broker.
        """
        self.logger.warning(f"Disconnected from MQTT broker: reason_code={reason_code}, flags={disconnect_flags}")


    def start(self, inifinite_loop: bool = True):
        """
        Start the MQTT Client.
        """
        # Set default callbacks
        self.mqtt_client.set_on_message(self.no_endpoint_message)
        self.mqtt_client.set_on_connect(self.on_connect)

        # Set will message and disconnect callback
        self.mqtt_client.set_will(topic=f"{self.id}/@/About", payload='{"status":{"state":"disconnected"}}', qos=1, retain=True)
        self.mqtt_client.client.on_disconnect = self.on_disconnect
        
        # Attempt to connect to broker
        while True:
            try:
                self.mqtt_client.connect(host=self.broker_socket[0], port=self.broker_socket[1], keepalive=CONNECT_RETRY_INTERVAL)
                break
            except ConnectionRefusedError as e:
                self.logger.error(f"Failed to connect to MQTT broker, is the broker running? Waiting {CONNECT_RETRY_INTERVAL} seconds before retrying.")
                time.sleep(CONNECT_RETRY_INTERVAL)
                continue
        
        # Start network loop
        self.mqtt_client.loop_start()
        
        # Keep service running
        self.logger.debug(f"{self.id} started successfully, entering main loop")
        while inifinite_loop:
            time.sleep(1)



# === MAIN LOOP ===


