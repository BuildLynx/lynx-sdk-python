"""
Service class for Lynx. A Service is the encapsulation of a single application or service, it contains Channels,
a Time Source, an MQTT Client, and has its own Endpoints.

Generative AI was used in the Creation/Modification of this file.
"""

from typing import Callable, Dict, Iterable, Optional, Sequence
import logging
import time

from lynx_sdk.core.client_component import ClientComponent
from lynx_sdk.core.channel import Channel
from lynx_sdk.messaging.time_source import TimeSource
from lynx_sdk.messaging.endpoint import InEndpoint, OutEndpoint
from lynx_sdk.messaging.mqtt_client import InboundMessage
from lynx_sdk.protocol.component_type import ComponentType
from lynx_sdk.protocol.schemas import \
    GET_ABOUT_ENDPOINT_ARGS, \
    SERVICE_SYS_ABOUT_ENDPOINT_ARGS, \
    SYS_NOTICE_ENDPOINT_ARGS, \
    SUBSCRIBE_ABOUT_ENDPOINT_ARGS
from lynx_sdk.protocol.capabilities import ChannelCommand
from lynx_sdk.protocol.contents import trim_payload_by_contents, PayloadBuildingError
from lynx_sdk.protocol.version import LYNX_VERSION
from lynx_sdk.runtime.notice_handler import LoggingNoticeHandler


class Service(ClientComponent):
    def __init__(self,
        id: str,
        title: str = "",
        description: str = "",
        lynx_version: str = LYNX_VERSION,
        time_source: Optional[TimeSource] = None,
        logger: Optional[logging.Logger] = None,
        publish_logs_as_notices: bool = True,
        track_network_state: bool = False):
        """
        Initialize a Lynx Service object.
        """
        super().__init__(
            id=id,
            component_type=ComponentType.SERVICE,
            title=title,
            description=description,
            lynx_version=lynx_version,
            time_source=time_source,
            logger=logger,
            track_network_state=track_network_state
        )

        self.channels: Dict[str, Channel] = {}

        self.sys_about_endpoint: OutEndpoint = self.new_out_endpoint(**SERVICE_SYS_ABOUT_ENDPOINT_ARGS)
        self.get_about_endpoint: InEndpoint = self.new_in_endpoint(self.about_handler, **GET_ABOUT_ENDPOINT_ARGS)
        self.sys_notice_endpoint: OutEndpoint = self.new_out_endpoint(**SYS_NOTICE_ENDPOINT_ARGS)
        if publish_logs_as_notices:
            self.logger.addHandler(LoggingNoticeHandler(endpoint=self.sys_notice_endpoint))

        if track_network_state:
            self.new_in_endpoint(self.network_state.update_from_about_message, **SUBSCRIBE_ABOUT_ENDPOINT_ARGS)

        self.client_endpoint_topics_set.update(set[str](self.endpoints.keys()))

    def freeze_interface(self) -> None:
        super().freeze_interface()
        for channel in self.channels.values():
            channel.freeze_interface()

    def service_deadlines(self) -> None:
        now_ns = time.perf_counter_ns()
        for channel in self.channels.values():
            channel.service_batcher(now_ns)

    def soonest_deadline_ns(self) -> Optional[int]:
        soonest: Optional[int] = None
        for channel in self.channels.values():
            deadline = channel.flush_deadline_ns()
            if deadline is None:
                continue
            if soonest is None or deadline < soonest:
                soonest = deadline
        return soonest

    def channel(
        self,
        id: str,
        title: str = "",
        description: str = "",
        output_data_schema: Optional[Dict] = None,
        sample_function: Optional[Callable] = None,
        config: Optional[Dict] = None,
        enable_poll: Optional[bool] = None,
        enable_stream: bool = True,
        enable_sample_interval: Optional[bool] = None,
        stream_fields: Optional[Iterable[str]] = None,
        commands: Optional[Sequence[ChannelCommand]] = None) -> Channel:
        """
        Create and register a Channel.

        Pass sample_function for a pulled source (Poll and sampleInterval advertised
        by default). Omit it for a pushed source; the application then calls
        channel.add_sample().
        """
        new_channel = Channel(
            id=id,
            service=self,
            title=title,
            description=description,
            sample_function=sample_function,
            output_data_schema=output_data_schema,
            config=config,
            enable_poll=enable_poll,
            enable_stream=enable_stream,
            enable_sample_interval=enable_sample_interval,
            stream_fields=stream_fields,
            commands=commands,
            lynx_version=self.lynx_version)
        self.add_channel(new_channel)
        return new_channel

    def new_channel(
        self,
        id: str,
        title: str = "",
        description: str = "",
        output_data_schema: Optional[Dict] = None,
        enable_poll: Optional[bool] = None,
        enable_stream: bool = True,
        enable_sample_interval: Optional[bool] = None,
        stream_fields: Optional[Iterable[str]] = None,
        commands: Optional[Sequence[ChannelCommand]] = None):
        """
        Decorator that creates a pulled Channel from a sample generator.
        """
        def decorator(sample_function: Callable):
            return self.channel(
                id=id,
                title=title,
                description=description,
                output_data_schema=output_data_schema,
                sample_function=sample_function,
                enable_poll=enable_poll,
                enable_stream=enable_stream,
                enable_sample_interval=enable_sample_interval,
                stream_fields=stream_fields,
                commands=commands)
        return decorator

    def add_channel(self, channel: Channel):
        """
        Add a channel to the service. Must complete before start() freezes the interface.
        """
        self.require_mutable_interface("add a channel")
        if channel.id in self.channels:
            raise ValueError(f"Channel with id {channel.id} already exists in service {self.id}")
        self.channels[channel.id] = channel
        self.client_endpoint_topics_set.update(set[str](channel.endpoints.keys()))

    def about_handler(self, msg: InboundMessage):
        """
        Handle incoming About queries.
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
        Produce a dictionary of information about the service.
        """
        return {
            "lynxType": "Service",
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
            "channels": {
                channel.id: channel.produce_about() for channel in self.channels.values()
            }
        }

    def publish_about(self):
        """
        Publish the about information to the MQTT broker.
        """
        self.sys_about_endpoint.publish(payload=self.produce_about(), qos=1, retain=True)
