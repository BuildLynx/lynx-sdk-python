"""
Channel capability units: a schema fragment plus the behavior it implies.

Generative AI was used in the Creation/Modification of this file.

Each command and each Stream field is a unit so the advertised interface and
the implementing behavior cannot drift. A Channel composes a set of these at
construction; after the first About publish the set is frozen.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from lynx_sdk.protocol.schemas import (
    CHANNEL_CMD_POLL_ENDPOINT_ARGS,
    CHANNEL_CMD_STOP_ENDPOINT_ARGS,
    CONTENTS_PROPERTY,
    REPLY_TOPIC_CLIENT_ABOUT,
    build_channel_out_data_endpoint_args,
)
from lynx_sdk.protocol.topics import validate_segment


RESERVED_ACTIONS = frozenset({"Poll", "Stream", "Stop"})
DISCOURAGED_ACTIONS = frozenset({"Start", "Pause", "Resume", "Reset", "Configure"})

STREAM_FIELD_CONTENTS = "contents"
STREAM_FIELD_SAMPLE_INTERVAL = "sampleInterval"
STREAM_FIELD_NUM_SAMPLES = "numSamples"
STREAM_FIELD_BATCH = "batch"

STREAM_FIELD_SCHEMAS: Dict[str, Dict] = {
    STREAM_FIELD_CONTENTS: CONTENTS_PROPERTY,
    STREAM_FIELD_SAMPLE_INTERVAL: {
        "title": "Sample Interval",
        "description": "Minimum seconds between admitted samples. Samples offered sooner are discarded. 0 = admit every sample the source offers.",
        "default": 1.0,
        "type": "number",
        "minimum": 0
    },
    STREAM_FIELD_NUM_SAMPLES: {
        "title": "Number of Samples",
        "description": "Total samples to admit into batches. 0 = infinite. Counts only samples admitted after rate and contents filtering.",
        "default": 0,
        "type": "integer",
        "minimum": 0
    },
    STREAM_FIELD_BATCH: {
        "title": "Batch",
        "description": "Flush limits for the open batch. Omitted object or omitted fields use the field defaults.",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "maxInterval": {
                "title": "Max Interval",
                "description": "Max seconds an open batch may wait before publish. 0 = no time limit (no empty keepalives).",
                "default": 300,
                "type": "number",
                "minimum": 0
            },
            "maxSamples": {
                "title": "Max Samples",
                "description": "Max samples per published message. 0 = no count limit.",
                "default": 1,
                "type": "integer",
                "minimum": 0
            }
        }
    }
}

ALL_STREAM_FIELDS: tuple[str, ...] = (
    STREAM_FIELD_CONTENTS,
    STREAM_FIELD_SAMPLE_INTERVAL,
    STREAM_FIELD_NUM_SAMPLES,
    STREAM_FIELD_BATCH,
)


class InterfaceFrozenError(RuntimeError):
    """Raised when a component's advertised interface is mutated after first About."""


class CapabilityError(ValueError):
    """Raised when a Channel's composed interface would violate protocol invariants."""


@dataclass
class ChannelCommand:
    """
    One Channel `!/{Action}` endpoint: schema fragment plus protocol role.

    long_running commands set status.command and require !/Stop.
    data_output commands require a `<` endpoint.
    """
    action: str
    description: str
    payload_properties: Optional[Dict] = None
    payload_schema: Optional[Dict] = None
    reply_topics: Optional[List[str]] = None
    data_output: Optional[bool] = None
    long_running: bool = False
    handler: Optional[Callable] = None
    extra_endpoint_args: Dict = field(default_factory=dict)

    def endpoint_args(self) -> Dict:
        args: Dict = {
            "topic": f"!/{self.action}",
            "description": self.description,
            **self.extra_endpoint_args,
        }
        if self.payload_schema is not None:
            args["payload_schema"] = self.payload_schema
        elif self.payload_properties is not None:
            args["payload_properties"] = self.payload_properties
        if self.reply_topics is not None:
            args["reply_topics"] = self.reply_topics
        if self.data_output is not None:
            args["data_output"] = self.data_output
        return args


def validate_action_name(action: str, *, allow_reserved: bool = False) -> str:
    """Validate a command action segment. Reserved names are rejected unless allow_reserved."""
    validate_segment(action, "command action")
    if not allow_reserved and action in RESERVED_ACTIONS:
        raise CapabilityError(
            f"{action!r} is a reserved command name with protocol-defined meaning. "
            "Use a different action, or enable the built-in."
        )
    return action


def poll_command() -> ChannelCommand:
    args = CHANNEL_CMD_POLL_ENDPOINT_ARGS
    return ChannelCommand(
        action="Poll",
        description=args["description"],
        payload_properties=args["payload_properties"],
        reply_topics=list(args["reply_topics"]),
        data_output=True,
        long_running=False,
    )


def stream_command(fields: Sequence[str] = ALL_STREAM_FIELDS) -> ChannelCommand:
    unknown = [name for name in fields if name not in STREAM_FIELD_SCHEMAS]
    if unknown:
        raise CapabilityError(f"Unknown Stream fields: {unknown}")
    properties = {name: STREAM_FIELD_SCHEMAS[name] for name in fields}
    return ChannelCommand(
        action="Stream",
        description="Start streaming on the channel, emitting data when available.",
        payload_properties=properties,
        reply_topics=[REPLY_TOPIC_CLIENT_ABOUT],
        data_output=True,
        long_running=True,
    )


def stop_command() -> ChannelCommand:
    args = CHANNEL_CMD_STOP_ENDPOINT_ARGS
    return ChannelCommand(
        action="Stop",
        description=args["description"],
        payload_properties=args["payload_properties"],
        reply_topics=list(args["reply_topics"]),
        data_output=False,
        long_running=False,
    )


def data_output_command_args(output_data_properties: Optional[Dict] = None) -> Dict:
    return build_channel_out_data_endpoint_args(output_data_properties)


def default_stream_fields(*, pulled: bool, enable_sample_interval: Optional[bool] = None) -> List[str]:
    """
    Stream payload fields advertised by default.

    Pulled sources advertise sampleInterval; pushed sources omit it unless the
    caller opts in.
    """
    fields = [STREAM_FIELD_CONTENTS, STREAM_FIELD_NUM_SAMPLES, STREAM_FIELD_BATCH]
    honors_interval = enable_sample_interval if enable_sample_interval is not None else pulled
    if honors_interval:
        fields.insert(1, STREAM_FIELD_SAMPLE_INTERVAL)
    return fields


def compose_channel_commands(
    *,
    pulled: bool,
    enable_poll: Optional[bool] = None,
    enable_stream: bool = True,
    stream_fields: Optional[Iterable[str]] = None,
    enable_sample_interval: Optional[bool] = None,
    custom_commands: Optional[Sequence[ChannelCommand]] = None) -> List[ChannelCommand]:
    """
    Build the command list for a Channel from capability flags.

    Invariants (A2.1 section 7.1) are checked here so an invalid composition
    fails at construction rather than advertising an unsatisfiable interface.
    """
    commands: List[ChannelCommand] = []
    include_poll = enable_poll if enable_poll is not None else pulled
    if include_poll:
        if not pulled:
            raise CapabilityError(
                "A Channel cannot advertise !/Poll unless it can produce a sample on demand. "
                "Pass a sample_function, or set enable_poll=False."
            )
        commands.append(poll_command())

    if enable_stream:
        fields = list(stream_fields) if stream_fields is not None else default_stream_fields(
            pulled=pulled, enable_sample_interval=enable_sample_interval)
        commands.append(stream_command(fields))

    if custom_commands:
        seen = {c.action for c in commands}
        for command in custom_commands:
            validate_action_name(command.action)
            if command.action in seen:
                raise CapabilityError(f"Duplicate command action {command.action!r}")
            seen.add(command.action)
            commands.append(command)

    long_running = any(c.long_running for c in commands)
    if long_running:
        commands.append(stop_command())
    elif any(c.action == "Stop" for c in commands):
        raise CapabilityError("!/Stop is only valid when a long-running command is present.")

    if not commands:
        raise CapabilityError("A Channel must declare at least one command endpoint.")

    return commands
