"""
MQTT Client wrapper for Lynx. Provides a unified interface for MQTT operations.
"""



# === IMPORTS ===

# -stdlib Imports-
from typing import Dict, Optional, Any, Callable

# -Lynx Imports-
from lynx_sdk.models.time_source import TimeSource

# -External Imports-
import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes
import orjson



# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===



#  === CLASSES ===

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
        print(f"Publishing message to topic {topic} with payload {payload} and properties {publish_properties}")
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


# === MAIN LOOP ===


