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
from lynx_sdk.models.endpoint import Endpoint, SubEndpoint, PubEndpoint

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
        logger: Optional[logging.Logger] = None):
        """
        Initialize a Lynx Client Component.
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
        self.logger.warning(f"Received message on topic \"{message.topic}\" but no endpoint is configured to handle it.")


    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict, reason_code: int, properties: mqtt.Properties):
        """
        Callback for when the client connects to the MQTT broker.
        """
        try:
            self.logger.debug(f"Connected to MQTT broker with result code {reason_code}")
            self.publish_about()
            self.mqtt_client.subscribe(f"{self.id}/#")
        except Exception as e:
            self.logger.error(f"Exception in on_connect: {e}", exc_info=True)
            raise
    
    
    def on_disconnect(self, client: mqtt.Client, userdata: Any, disconnect_flags: Dict, reason_code: int, properties: mqtt.Properties):
        """
        Callback for when the client disconnects from the MQTT broker.
        """
        self.logger.warning(f"Disconnected from MQTT broker: reason_code={reason_code}, flags={disconnect_flags}")


    def start(self):
        """
        Start the MQTT Client.
        """
        # Set default callbacks
        self.mqtt_client.set_on_message(self.no_endpoint_message)
        self.mqtt_client.set_on_connect(self.on_connect)
        self.mqtt_client.client.on_disconnect = self.on_disconnect

        self.mqtt_client.set_will(topic=f"{self.id}/@/About", payload='{"status":{"state":"offline"}}', qos=1, retain=True)
        
        # Connect to broker
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
        while True:
            time.sleep(1)



# === MAIN LOOP ===


