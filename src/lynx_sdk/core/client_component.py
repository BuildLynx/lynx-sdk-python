"""
Client Component base class for Lynx. A Client Component is a component that has its own MQTT client (like Service or Node).

Generative AI was used in the Creation/Modification of this file.

Broker resolution and logger construction live in lynx_sdk.runtime. MQTT
lifecycle and the serve loop are kept here rather than in Component.
start(loop="thread") runs paho's network thread and a deadline loop;
start(loop="pumped") connects and returns so the application can call pump().
"""

import logging
from typing import Dict, Any, Optional, Tuple
import time

from lynx_sdk.core.component import Component
from lynx_sdk.messaging.mqtt_client import MqttClient
from lynx_sdk.messaging.time_source import TimeSource, instantiate_ideal_time_source
from lynx_sdk.protocol.component_type import ComponentType
from lynx_sdk.runtime.broker_config import resolve_broker_socket
from lynx_sdk.runtime.logging_setup import configure_logger
from lynx_sdk.runtime.network_state import NetworkState

import paho.mqtt.client as mqtt


CONNECT_RETRY_INTERVAL: int = 5
KEEPALIVE_INTERVAL: int = 60
DEADLINE_SLEEP_CAP_S: float = 0.1


class ClientComponent(Component):
    def __init__(self,
        id: str,
        component_type: ComponentType,
        title: str,
        description: str,
        lynx_version: str,
        time_source: Optional[TimeSource] = None,
        logger: Optional[logging.Logger] = None,
        track_network_state: bool = False):
        """
        Initialize a Lynx Client Component.
        """
        logger = configure_logger(id, logger)
        time_source = time_source or instantiate_ideal_time_source()
        mqtt_client = MqttClient(client_id=id, time_source=time_source)

        super().__init__(
            id=id,
            component_type=component_type,
            title=title,
            description=description,
            lynx_version=lynx_version,
            owner_id=id,
            logger=logger,
            mqtt_client=mqtt_client)

        self._status = {"connected": False}

        self.broker_socket: Tuple[str, int] = resolve_broker_socket()
        self.time_source: TimeSource = time_source
        self.client_endpoint_topics_set: set[str] = set[str]()
        self.network_state: Optional[NetworkState] = NetworkState() if track_network_state else None
        self._running: bool = False


    def publish_about(self) -> Dict:
        raise NotImplementedError


    def no_endpoint_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage):
        """
        Emit a notice that the service received a message on an endpoint that is not configured.
        """
        if message.topic in self.client_endpoint_topics_set:
            return
        if not message.topic.startswith(f"{self.id}/"):
            return
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
            self.mqtt_client.subscribe(subscribe_topic_filter, qos=2)

            self.set_status(connected=True)
            self.publish_about()
        except Exception as e:
            self.logger.error(f"Exception in on_connect: {e}", exc_info=True)
            raise


    def on_disconnect(self, client: mqtt.Client, userdata: Any, disconnect_flags: Dict, reason_code: int, properties: mqtt.Properties):
        """
        Callback for when the client disconnects from the MQTT broker.
        """
        self.set_status(connected=False)
        self.logger.warning(f"Disconnected from MQTT broker: reason_code={reason_code}, flags={disconnect_flags}")


    def service_deadlines(self) -> None:
        """Flush any due protocol deadlines. Services override this to pump Channels."""
        return


    def soonest_deadline_ns(self) -> Optional[int]:
        """perf_counter_ns of the next protocol deadline, or None."""
        return None


    def pump(self, timeout: float = 0.1) -> None:
        """
        Process MQTT traffic once and service protocol deadlines.

        This is the single-threaded / user-owned loop entry point (loop="pumped").
        Command handlers run on the thread that calls pump().
        """
        self.mqtt_client.loop(timeout=timeout)
        self.service_deadlines()


    def _connect_with_retry(self) -> None:
        self.mqtt_client.set_on_message(self.no_endpoint_message)
        self.mqtt_client.set_on_connect(self.on_connect)
        self.mqtt_client.set_will(topic=f"{self.id}/@/About", payload='{"status":{"connected":false}}', qos=1, retain=True)
        self.mqtt_client.client.on_disconnect = self.on_disconnect

        while True:
            try:
                self.mqtt_client.connect(host=self.broker_socket[0], port=self.broker_socket[1], keepalive=KEEPALIVE_INTERVAL)
                break
            except ConnectionRefusedError:
                self.logger.error(
                    f"Failed to connect to MQTT broker ({self.broker_socket[0]}:{self.broker_socket[1]}), "
                    f"is the broker running? Waiting {CONNECT_RETRY_INTERVAL} seconds before retrying.")
                time.sleep(CONNECT_RETRY_INTERVAL)


    def _run_deadline_loop(self) -> None:
        """Sleep until the next batch deadline (capped) and flush. MQTT runs on paho's thread."""
        self._running = True
        while self._running:
            deadline = self.soonest_deadline_ns()
            if deadline is None:
                time.sleep(DEADLINE_SLEEP_CAP_S)
            else:
                remaining = (deadline - time.perf_counter_ns()) / 1_000_000_000
                time.sleep(max(0.0, min(remaining, DEADLINE_SLEEP_CAP_S)))
            self.service_deadlines()


    def start(self, infinite_loop: bool = True, loop: str = "thread"):
        """
        Connect to the broker and begin serving.

        The advertised interface is frozen here, before connect, so the first
        @/About cannot change afterwards.

        Args:
            infinite_loop: When loop="thread", block until stopped.
            loop: "thread" starts paho's background network loop. "pumped" connects
                and returns; the caller must invoke pump() regularly.
        """
        if loop not in ("thread", "pumped"):
            raise ValueError(f"loop must be 'thread' or 'pumped', got {loop!r}")

        self.freeze_interface()
        self._connect_with_retry()

        if loop == "pumped":
            self.logger.debug(f"{self.id} connected in pumped mode; call pump() to serve")
            return

        self.mqtt_client.loop_start()
        self.logger.debug(f"{self.id} started successfully, entering main loop")
        if infinite_loop:
            self._run_deadline_loop()
