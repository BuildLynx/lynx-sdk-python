"""
Channel class for Lynx. A Channel is the encapsulation of a single input and/or output data stream.

Generative AI was used in the Creation/Modification of this file.

The advertised command set is composed from capabilities (A2.1 section 7.1)
at interface freeze. Long-running command concurrency lives in ActiveCommand;
admission, batching, and the sampleInterval gate live in ActiveStream. This
class binds those to MQTT and, for pulled sources, an optional sample thread.
"""

from __future__ import annotations
from typing import Callable, Dict, Any, Iterable, Optional, Sequence, TYPE_CHECKING
import threading

from lynx_sdk.core.component import Component
from lynx_sdk.messaging.endpoint import OutEndpoint
from lynx_sdk.messaging.mqtt_client import InboundMessage
from lynx_sdk.protocol.capabilities import (
    DISCOURAGED_ACTIONS,
    STREAM_FIELD_SAMPLE_INTERVAL,
    ChannelCommand,
    CapabilityError,
    compose_channel_commands,
    data_output_endpoint_args,
    validate_action_name,
)
from lynx_sdk.protocol.component_type import ComponentType
from lynx_sdk.protocol.contents import trim_payload_by_contents, PayloadBuildingError
from lynx_sdk.protocol.version import LYNX_VERSION
from lynx_sdk.runtime.active_command import ActiveCommand
from lynx_sdk.runtime.active_stream import (
    ActiveStream,
    DEFAULT_SAMPLE_INTERVAL,
    DEFAULT_TOTAL_SAMPLE_LIMIT,
    resolve_batch_limits,
)

if TYPE_CHECKING:
    from lynx_sdk.core.service import Service


class Channel(Component):
    def __init__(self,
        id: str,
        service: Service,
        sample_function: Optional[Callable] = None,
        title: str = "",
        description: str = "",
        output_data_properties: Optional[Dict] = None,
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
            output_data_properties: Map of property name to subschema for the channel's data.
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
        self._active_stream: Optional[ActiveStream] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._active_command = ActiveCommand()

        self._enable_poll = enable_poll
        self._enable_stream = enable_stream
        self._enable_sample_interval = enable_sample_interval
        self._declared_stream_fields: Optional[list[str]] = (
            list(stream_fields) if stream_fields is not None else None)
        self._output_data_properties = output_data_properties
        self._custom_commands: list[ChannelCommand] = list(commands) if commands else []
        self._commands: list[ChannelCommand] = []
        self._stream_fields: set[str] = set()
        self._honors_sample_interval = False

        self.cmd_poll_endpoint = None
        self.cmd_stream_endpoint = None
        self.cmd_stop_endpoint = None
        self.out_data_endpoint: Optional[OutEndpoint] = None

        self.config: Dict[str, Any] = config if config is not None else {"streamOnStartup": False}

    def __call__(self, sample_function: Callable) -> Channel:
        """Attach a sample generator so Service.channel() can be used as a decorator."""
        self.require_mutable_interface("attach a sample source")
        if self._sample_function is not None:
            raise CapabilityError(
                f"Channel '{self.id}' already has a sample function; cannot attach another.")
        self._sample_function = sample_function
        return self

    def freeze_interface(self) -> None:
        if self._interface_frozen:
            return

        self._commands = compose_channel_commands(
            pulled=self._sample_function is not None,
            enable_poll=self._enable_poll,
            enable_stream=self._enable_stream,
            stream_fields=self._declared_stream_fields,
            enable_sample_interval=self._enable_sample_interval,
            custom_commands=self._custom_commands)

        stream_cmd = next((c for c in self._commands if c.action == "Stream"), None)
        if stream_cmd is not None and stream_cmd.payload_properties is not None:
            self._stream_fields = set(stream_cmd.payload_properties.keys())
        else:
            self._stream_fields = set()
        self._honors_sample_interval = STREAM_FIELD_SAMPLE_INTERVAL in self._stream_fields

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
            self.out_data_endpoint = self.new_out_endpoint(
                **data_output_endpoint_args(self._output_data_properties))

        super().freeze_interface()

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
                if not self._active_command.try_begin(action, msg.payload):
                    self.logger.warning(
                        f"Channel '{self.id}' is busy, ignoring {action} request.")
                    return
                self.set_status(command=self._active_command.snapshot())
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

        Endpoints are created at interface freeze. Guards here check declared
        intent: dataOutput requires that a '<' endpoint will exist (Stream,
        Poll, or an earlier data-producing command).
        """
        self.require_mutable_interface("add a command")
        validate_action_name(action)
        if action in DISCOURAGED_ACTIONS:
            self.logger.warning(
                f"Command action {action!r} is a common verb reserved for possible future "
                "built-ins. Prefer an application-prefixed name such as 'AcmeCalibrate'.")
        if any(c.action == action for c in self._custom_commands):
            raise CapabilityError(f"Channel '{self.id}' already has command {action!r}")
        if data_output and not self._will_have_data_endpoint():
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
        self._custom_commands.append(command)
        return command

    def _will_have_data_endpoint(self) -> bool:
        if self._enable_stream:
            return True
        include_poll = (
            self._enable_poll if self._enable_poll is not None
            else self._sample_function is not None)
        if include_poll:
            return True
        return any(c.data_output for c in self._custom_commands)

    def add_sample(self, data: Any) -> bool:
        """
        Offer a sample to the active stream.

        Discarded when no stream is active. When sampleInterval is advertised,
        samples offered too soon are also discarded. The return value is whether
        the stream is still open, not whether the sample was admitted.
        """
        active_stream = self._active_stream
        if active_stream is None:
            return False
        return active_stream.add_sample(data)

    def flush_if_due(self, now_ns: Optional[int] = None) -> None:
        """Let a scheduler flush the open batch if its deadline has passed."""
        if self._active_stream is not None:
            self._active_stream.flush_if_due(now_ns)

    def flush_deadline_ns(self) -> Optional[int]:
        if self._active_stream is None:
            return None
        return self._active_stream.flush_deadline_ns()

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
        if not self._active_command.try_begin("Stream", msg.payload):
            self.logger.warning(
                f"Channel '{self.id}' is already running a command, ignoring stream start request.")
            return

        payload = msg.payload
        contents = payload.get("contents", True)
        total_sample_limit = int(payload.get("numSamples", DEFAULT_TOTAL_SAMPLE_LIMIT))
        limits = resolve_batch_limits(payload)
        sample_interval: Optional[float] = None
        if self._honors_sample_interval:
            sample_interval = float(payload.get("sampleInterval", DEFAULT_SAMPLE_INTERVAL))

        self._exit_flag.clear()
        self.set_status(command=self._active_command.snapshot())
        active_stream = ActiveStream(
            contents=contents,
            max_interval=limits.max_interval,
            batch_size_limit=limits.batch_size_limit,
            total_sample_limit=total_sample_limit,
            publish=self._publish_data,
            logger=self.logger,
            on_ended=self._on_stream_ended,
            sample_interval=sample_interval)
        active_stream.start_stream()
        self._active_stream = active_stream

        if self._sample_function is not None:
            stream_thread = threading.Thread(
                target=self._stream_handler,
                kwargs={"request": msg, "active_stream": active_stream},
                daemon=True)
            self._stream_thread = stream_thread
            stream_thread.start()

    def _publish_data(self, payload: Any) -> None:
        if self.out_data_endpoint is None:
            return
        self.out_data_endpoint.publish(payload=payload)

    def _on_stream_ended(self):
        self._exit_flag.set()
        self._active_command.end()
        self.set_status(command=None)

    def _stream_handler(self, request: InboundMessage, active_stream: ActiveStream):
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
                if not active_stream.add_sample(data):
                    break
        finally:
            active_stream.end_stream()

    def stop_handler(self, msg: InboundMessage):
        """Stop the active command. No-op when idle; produces no data message then."""
        self._exit_flag.set()
        if self._active_stream is not None:
            self._active_stream.end_stream()
            return
        if self._active_command.end():
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
