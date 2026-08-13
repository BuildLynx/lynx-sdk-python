"""
Channel class for Lynx. A Channel is the encapsulation of a single input and/or output data stream.

Generative AI was used in the Creation/Modification of this file.

The advertised command set is composed from capabilities (A2.1 section 7.1).
Long-running command concurrency lives in CommandMachine; batching and the
sampleInterval gate live in StreamBatcher. This class binds those to MQTT and,
for pulled sources, an optional sample thread.
"""

from __future__ import annotations
from typing import Callable, Dict, Any, Iterable, Optional, Sequence, TYPE_CHECKING
import threading

from lynx_sdk.components.component import Component, ComponentType
from lynx_sdk.models.endpoint import OutEndpoint
from lynx_sdk.protocol.capabilities import (
    DISCOURAGED_ACTIONS,
    STREAM_FIELD_SAMPLE_INTERVAL,
    ChannelCommand,
    CapabilityError,
    compose_channel_commands,
    data_output_command_args,
    stop_command,
    validate_action_name,
)
from lynx_sdk.protocol.command_machine import CommandMachine
from lynx_sdk.protocol.stream_batcher import (
    StreamBatcher,
    DEFAULT_NUM_SAMPLES,
    DEFAULT_SAMPLE_INTERVAL,
    resolve_batch_limits,
)
from lynx_sdk.utils.json_tools import trim_payload_by_contents, PayloadBuildingError
from lynx_sdk.utils.mqtt_client import InboundMessage
from lynx_sdk.utils.structures import LYNX_VERSION

if TYPE_CHECKING:
    from lynx_sdk.components.service import Service


class Channel(Component):
    def __init__(self,
        id: str,
        service: Service,
        sample_function: Optional[Callable] = None,
        title: str = "",
        description: str = "",
        output_data_schema: Optional[Dict] = None,
        config: Optional[Dict[str, Any]] = None,
        enable_poll: Optional[bool] = None,
        enable_stream: bool = True,
        enable_sample_interval: Optional[bool] = None,
        stream_fields: Optional[Iterable[str]] = None,
        commands: Optional[Sequence[ChannelCommand]] = None,
        lynx_version: str = LYNX_VERSION):
        """
        Initialize a Lynx Channel object.

        Args:
            id: Unique identifier for this channel
            service: Parent service this channel belongs to
            sample_function: Optional generator that yields samples on demand. Present
                implies a pulled source: !/Poll and sampleInterval are advertised unless
                overridden. Absent implies a pushed source: the application calls
                add_sample().
            title: Human-readable title
            description: Human-readable description
            output_data_schema: Map of property name to subschema for the channel's data.
            config: Configuration for the channel
            enable_poll: Advertise !/Poll. Defaults to True iff sample_function is set.
            enable_stream: Advertise !/Stream (and !/Stop). Default True.
            enable_sample_interval: Advertise and honor sampleInterval on Stream.
                Defaults to True iff sample_function is set.
            stream_fields: Explicit Stream payload fields. Overrides enable_sample_interval
                when provided.
            commands: Additional user-defined ChannelCommand values.
            lynx_version: Lynx protocol version
        """
        super().__init__(
            id=id,
            component_type=ComponentType.CHANNEL,
            title=title,
            description=description,
            lynx_version=lynx_version,
            owner_id=service.id,
            logger=service.logger,
            mqtt_client=service.mqtt_client,
        )

        self._status = {"command": None}

        self.service: Service = service
        self._sample_function: Optional[Callable] = sample_function
        self._exit_flag: threading.Event = threading.Event()
        self._stream_batcher: Optional[StreamBatcher] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._command_machine = CommandMachine()

        pulled = sample_function is not None
        self._commands: list[ChannelCommand] = compose_channel_commands(
            pulled=pulled,
            enable_poll=enable_poll,
            enable_stream=enable_stream,
            stream_fields=stream_fields,
            enable_sample_interval=enable_sample_interval,
            custom_commands=commands)

        stream_cmd = next((c for c in self._commands if c.action == "Stream"), None)
        if stream_cmd is not None and stream_cmd.payload_properties is not None:
            self._stream_fields = set(stream_cmd.payload_properties.keys())
        else:
            self._stream_fields = set()
        self._honors_sample_interval = STREAM_FIELD_SAMPLE_INTERVAL in self._stream_fields

        self.cmd_poll_endpoint = None
        self.cmd_stream_endpoint = None
        self.cmd_stop_endpoint = None
        for command in self._commands:
            endpoint = self.new_in_endpoint(self._handler_for(command), **command.endpoint_args())
            if command.action == "Poll":
                self.cmd_poll_endpoint = endpoint
            elif command.action == "Stream":
                self.cmd_stream_endpoint = endpoint
            elif command.action == "Stop":
                self.cmd_stop_endpoint = endpoint

        produces_data = any(c.data_output for c in self._commands)
        if produces_data:
            self.out_data_endpoint: Optional[OutEndpoint] = self.new_out_endpoint(
                **data_output_command_args(output_data_schema))
        else:
            self.out_data_endpoint = None

        self.config: Dict[str, Any] = config if config is not None else {"streamOnStartup": False}
        if self.config.get("streamOnStartup", False):
            self.start_stream_handler(msg=InboundMessage(topic="", payload={"contents": True}))

    def _handler_for(self, command: ChannelCommand) -> Callable:
        if command.action == "Poll":
            return self.poll_handler
        if command.action == "Stream":
            return self.start_stream_handler
        if command.action == "Stop":
            return self.stop_handler
        if command.handler is None:
            raise CapabilityError(f"Custom command {command.action!r} has no handler")
        if command.long_running:
            user_handler = command.handler
            action = command.action

            def long_running_handler(msg: InboundMessage):
                if not self._command_machine.try_begin(action, msg.payload):
                    self.logger.warning(
                        f"Channel '{self.id}' is busy, ignoring {action} request.")
                    return
                self.set_status(command=self._command_machine.active)
                return user_handler(msg)

            return long_running_handler
        return command.handler

    def add_command(
        self,
        action: str,
        handler: Callable,
        *,
        description: str = "",
        payload_properties: Optional[Dict] = None,
        payload_schema: Optional[Dict] = None,
        reply_topics: Optional[list] = None,
        data_output: bool = False,
        long_running: bool = False) -> ChannelCommand:
        """
        Add a user-defined !/{Action} command. Must be called before the Service starts.
        """
        self.require_mutable_interface("add a command")
        validate_action_name(action)
        if action in DISCOURAGED_ACTIONS:
            self.logger.warning(
                f"Command action {action!r} is a common verb reserved for possible future "
                "built-ins. Prefer an application-prefixed name such as 'AcmeCalibrate'.")
        if any(c.action == action for c in self._commands):
            raise CapabilityError(f"Channel '{self.id}' already has command {action!r}")
        if long_running and self.cmd_stop_endpoint is None:
            stop = stop_command()
            self._commands.append(stop)
            self.cmd_stop_endpoint = self.new_in_endpoint(self.stop_handler, **stop.endpoint_args())
        if data_output and self.out_data_endpoint is None:
            raise CapabilityError(
                f"Command {action!r} declares dataOutput but this channel has no '<' endpoint. "
                "Enable Stream or another data-producing command first.")
        command = ChannelCommand(
            action=action,
            description=description or f"Custom command {action}",
            payload_properties={} if payload_properties is None and payload_schema is None else payload_properties,
            payload_schema=payload_schema,
            reply_topics=[] if reply_topics is None else reply_topics,
            data_output=data_output,
            long_running=long_running,
            handler=handler)
        self._commands.append(command)
        self.new_in_endpoint(self._handler_for(command), **command.endpoint_args())
        return command

    def add_sample(self, data: Any) -> bool:
        """
        Offer a sample to the active stream.

        Discarded when no stream is active. When sampleInterval is advertised,
        samples offered too soon are also discarded by the batcher.
        """
        batcher = self._stream_batcher
        if batcher is None:
            return False
        return batcher.add_sample(data)

    def service_batcher(self, now_ns: Optional[int] = None) -> None:
        """Let a scheduler flush the open batch if its deadline has passed."""
        if self._stream_batcher is not None:
            self._stream_batcher.service(now_ns)

    def flush_deadline_ns(self) -> Optional[int]:
        if self._stream_batcher is None:
            return None
        return self._stream_batcher.flush_deadline_ns()

    def poll_handler(self, msg: InboundMessage):
        """Handle a poll request: one sample, no status.command change."""
        if self._sample_function is None or self.out_data_endpoint is None:
            self.logger.warning(f"Channel '{self.id}' cannot Poll: no on-demand source.")
            return
        contents = msg.payload.get("contents", True)

        for data in self._sample_function(request=msg, continue_sampling=lambda **kwargs: True):
            if contents is not True:
                try:
                    data = trim_payload_by_contents(data, contents)
                except PayloadBuildingError as e:
                    self.logger.error(f"Error trimming payload: {e.message}")
                    return
            self.out_data_endpoint.publish(payload=[{"s": 0, "ns": 0, "data": data}])
            break

    def start_stream_handler(self, msg: InboundMessage):
        """Handle a stream start request."""
        if not self._command_machine.try_begin("Stream", msg.payload):
            self.logger.warning(
                f"Channel '{self.id}' is already running a command, ignoring stream start request.")
            return

        payload = msg.payload
        contents = payload.get("contents", True)
        num_samples = int(payload.get("numSamples", DEFAULT_NUM_SAMPLES))
        max_interval, max_samples = resolve_batch_limits(payload)
        sample_interval: Optional[float] = None
        if self._honors_sample_interval:
            sample_interval = float(payload.get("sampleInterval", DEFAULT_SAMPLE_INTERVAL))

        self._exit_flag.clear()
        self.set_status(command=self._command_machine.active)
        batcher = StreamBatcher(
            contents=contents,
            max_interval=max_interval,
            max_samples=max_samples,
            num_samples=num_samples,
            publish=self._publish_data,
            logger=self.logger,
            on_ended=self._on_stream_ended,
            sample_interval=sample_interval)
        batcher.start()
        self._stream_batcher = batcher

        if self._sample_function is not None:
            stream_thread = threading.Thread(
                target=self._stream_handler,
                kwargs={"request": msg, "batcher": batcher},
                daemon=True)
            self._stream_thread = stream_thread
            stream_thread.start()

    def _publish_data(self, payload: Any) -> None:
        if self.out_data_endpoint is None:
            return
        self.out_data_endpoint.publish(payload=payload)

    def _on_stream_ended(self):
        self._exit_flag.set()
        self._command_machine.end()
        self.set_status(command=None)

    def _stream_handler(self, request: InboundMessage, batcher: StreamBatcher):
        def continue_sampling(default_interval: float = DEFAULT_SAMPLE_INTERVAL):
            if self._honors_sample_interval:
                interval = request.payload.get("sampleInterval", default_interval)
            else:
                interval = default_interval
            return not self._exit_flag.wait(timeout=interval)

        try:
            for data in self._sample_function(request=request, continue_sampling=continue_sampling):
                if self._exit_flag.is_set():
                    break
                if not batcher.add_sample(data):
                    break
        finally:
            batcher.end_stream()

    def stop_handler(self, msg: InboundMessage):
        """Stop the active command. No-op when idle; produces no data message then."""
        self._exit_flag.set()
        if self._stream_batcher is not None:
            self._stream_batcher.end_stream()
            return
        if self._command_machine.end():
            self.set_status(command=None)

    def produce_about(self) -> Dict:
        return {
            "lynxType": "Channel",
            "docs": {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "lynx_version": self.lynx_version,
            },
            "config": {},
            "status": self.get_status_dict(),
            "endpoints": {
                endpoint.topic: endpoint.produce_about() for endpoint in self.endpoints.values()
            }
        }

    def set_status(self, command: Optional[Dict[str, Any]] = None) -> bool:
        """
        Set command status and publish a partial About when it changes.
        """
        changed = super().set_status(command=command)
        if changed:
            payload = {"channels": {self.id: {"status": self.get_status_dict()}}}
            self.service.sys_about_endpoint.publish(payload=payload)
        return changed
