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
from lynx_sdk.protocol.component_type import ComponentType
from lynx_sdk.protocol.schemas import SERVICE_SYS_ABOUT_ENDPOINT_ARGS
from lynx_sdk.protocol.capabilities import ChannelCommand
from lynx_sdk.protocol.version import LYNX_VERSION


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
            sys_about_endpoint_args=SERVICE_SYS_ABOUT_ENDPOINT_ARGS,
            time_source=time_source,
            logger=logger,
            track_network_state=track_network_state,
            publish_logs_as_notices=publish_logs_as_notices)

        self.channels: Dict[str, Channel] = {}

    def freeze_interface(self) -> None:
        if self._interface_frozen:
            return
        for channel in self.channels.values():
            channel.freeze_interface()
            self.client_endpoint_topics_set.update(set(channel.endpoints.keys()))
        super().freeze_interface()

    def flush_due_deadlines(self) -> None:
        now_ns = time.perf_counter_ns()
        for channel in self.channels.values():
            channel.flush_if_due(now_ns)

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
        output_data_properties: Optional[Dict] = None,
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

        May be used as a decorator: `@service.channel("id", ...)` attaches the
        decorated generator as the sample function and binds the name to the Channel.
        """
        new_channel = Channel(
            id=id,
            service=self,
            title=title,
            description=description,
            sample_function=sample_function,
            output_data_properties=output_data_properties,
            config=config,
            enable_poll=enable_poll,
            enable_stream=enable_stream,
            enable_sample_interval=enable_sample_interval,
            stream_fields=stream_fields,
            commands=commands,
            lynx_version=self.lynx_version)
        self.add_channel(new_channel)
        return new_channel

    def add_channel(self, channel: Channel):
        """
        Add a channel to the service. Must complete before start() freezes the interface.
        """
        self.require_mutable_interface("add a channel")
        if channel.id in self.channels:
            raise ValueError(f"Channel with id {channel.id} already exists in service {self.id}")
        self.channels[channel.id] = channel

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
