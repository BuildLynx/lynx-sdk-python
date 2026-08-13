"""
MQTT Client wrapper for Lynx. Provides a unified interface for MQTT operations.

Generative AI was used in the Creation/Modification of this file.
"""



# === IMPORTS ===

# -stdlib Imports-
from dataclasses import dataclass
from typing import Dict, Optional, Any, Callable

# -Lynx Imports-
from lynx_sdk.messaging.time_source import TimeSource

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
class InboundMessage:
    """
    Normalized inbound MQTT message passed to Lynx SubEndpoint handlers.
    """
    topic: str
    payload: Dict
    sec: Optional[int] = None
    nsec: Optional[int] = None
    qos: Optional[int] = None
    retain: Optional[bool] = None
    raw: Optional[bytes] = None
    properties: Optional[Dict[str, str]] = None


class MqttClient:
    """
    MQTT client wrapper for Lynx with paho-mqtt backend.
    
    This wrapper provides:
    - Automatic timestamp injection via TimeSource
    - JSON encoding of payloads
    - MQTT v5 user properties support
    - Simplified API for Lynx components
    """
    
    def __init__(
        self,
        client_id: str,
        time_source: TimeSource,
        paho_client: Optional[mqtt.Client] = None):
        """
        Initialize a Paho MQTT client wrapper.
        
        Args:
            client_id: Unique identifier for this MQTT client
            time_source: Time source for automatic timestamp injection
            paho_client: Existing paho client to wrap, or None to create a new one
        """
        self.client_id = client_id
        self.time_source = time_source
        
        if paho_client is not None:
            self.client = paho_client
        else:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                protocol=mqtt.MQTTv5
            )
    
    
    def publish(
        self,
        topic: str,
        payload: Dict,
        qos: int = 0,
        retain: bool = False,
        properties: Optional[Dict[str, str]] = None,
        add_timestamp: bool = True
    ) -> Optional[mqtt.MQTTMessageInfo]:
        """
        Publish a message to an MQTT topic with automatic timestamp injection.
        
        Args:
            topic: MQTT topic to publish to
            payload: Dictionary payload to publish (will be JSON-encoded)
            qos: Quality of Service level (0, 1, or 2)
            retain: Whether to retain the message on the broker
            properties: Additional MQTT v5 user properties
            add_timestamp: Whether to automatically add sec/nsec timestamps
            
        Returns:
            MQTTMessageInfo or None if publish failed
        """
        properties = properties or {}
        
        # Create MQTT v5 properties
        publish_properties = Properties(PacketTypes.PUBLISH)
        
        # Add timestamp if requested and not already present
        if add_timestamp and "s" not in properties and "ns" not in properties:
            publish_time = self.time_source.get_time()
            properties["s"] = str(publish_time['s'])
            properties["ns"] = str(publish_time['ns'])
        
        # Add all user properties
        for key, value in properties.items():
            publish_properties.UserProperty = (key, value)
        
        # Publish the message
        message_info: mqtt.MQTTMessageInfo = self.client.publish(
            topic=topic,
            payload=orjson.dumps(payload),
            qos=qos,
            retain=retain,
            properties=publish_properties
        )  # Wait for the publish to complete
        return message_info
    
    
    def subscribe(self, topic: str, qos: int = 0) -> Any:
        """
        Subscribe to an MQTT topic.
        
        Args:
            topic: MQTT topic or topic filter to subscribe to
            qos: Quality of Service level (0, 1, or 2)
            
        Returns:
            Tuple of (result, message_id)
        """
        return self.client.subscribe(topic, qos)
    
    
    def add_callback(self, topic: str, callback: Callable) -> None:
        """
        Add a message callback for a specific topic.
        
        Args:
            topic: MQTT topic or topic filter
            callback: Callback function with signature (client, userdata, message)
        """
        self.client.message_callback_add(topic, callback)
    

    def remove_callback(self, topic: str) -> None:
        """
        Remove a message callback for a specific topic.
        
        Args:
            topic: MQTT topic or topic filter
        """
        self.client.message_callback_remove(topic)
    
    
    def connect(self, host: str, port: int = 1883, keepalive: int = 60) -> None:
        """
        Connect to an MQTT broker.
        
        Args:
            host: Broker hostname or IP address
            port: Broker port (default 1883)
            keepalive: Keepalive interval in seconds
        """
        self.client.connect(host=host, port=port, keepalive=keepalive)
    
    
    def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        self.client.disconnect()
    
    
    def loop_start(self) -> None:
        """Start the network loop in a background thread."""
        self.client.loop_start()

    def loop(self, timeout: float = 1.0) -> int:
        """
        Process network events once. Used by pumped (user-owned) serve loops.

        Handlers registered on InEndpoints run on the calling thread.
        """
        return self.client.loop(timeout=timeout)
    
    
    def loop_stop(self) -> None:
        """Stop the background network loop."""
        self.client.loop_stop()
    
    
    def set_on_connect(self, callback: Callable) -> None:
        """
        Set the on_connect callback.
        
        Args:
            callback: Callback function for connection events
        """
        self.client.on_connect = callback
    
    
    def set_on_message(self, callback: Callable) -> None:
        """
        Set the default on_message callback.
        
        Args:
            callback: Callback function for messages not matched by specific callbacks
        """
        self.client.on_message = callback
    

    def set_will(self, topic: str, payload: str, qos: int = 1, retain: bool = True) -> None:
        """
        Set the will message for the client.
        
        Args:
            topic: MQTT topic to publish the will message to
            payload: Payload to publish with the will message
            qos: Quality of Service level (0, 1, or 2)
            retain: Whether to retain the will message on the broker
        """
        self.client.will_set(topic=topic, payload=payload, qos=qos, retain=retain)


    @staticmethod
    def from_paho_message(message: mqtt.MQTTMessage, payload: Dict) -> InboundMessage:
        """
        Build an InboundMessage from a paho MQTTMessage and parsed payload.
        """
        sec: Optional[int] = None
        nsec: Optional[int] = None
        parsed_properties: Dict[str, str] = {}

        message_properties = getattr(message, "properties", None)
        user_properties = getattr(message_properties, "UserProperty", None)
        if user_properties is None:
            user_properties = []

        for key, value in user_properties:
            if key == "s":
                try:
                    sec = int(value)
                except (TypeError, ValueError):
                    parsed_properties[str(key)] = str(value)
            elif key == "ns":
                try:
                    nsec = int(value)
                except (TypeError, ValueError):
                    parsed_properties[str(key)] = str(value)
            else:
                parsed_properties[str(key)] = str(value)

        return InboundMessage(
            topic=str(message.topic),
            payload=payload,
            sec=sec,
            nsec=nsec,
            qos=message.qos,
            retain=message.retain,
            raw=bytes(message.payload),
            properties=parsed_properties
        )


# === MAIN LOOP ===


