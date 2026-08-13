"""
Pure topic construction for Lynx components.

Generative AI was used in the Creation/Modification of this file.

Topic strings are a protocol concern: they follow from component identity and a
suffix such as `@/About` or `!/Stream`. They do not depend on MQTT, loggers, or
which Python class owns the connection.
"""

from typing import Optional


def validate_segment(value: str, kind: str = "segment") -> str:
    """
    A component id, channel id, or command action occupies exactly one MQTT topic
    segment: non-empty, no `/`, and no wildcards.

    Args:
        value: The candidate segment.
        kind: Label used in error messages.

    Returns:
        The same string, if valid.

    Raises:
        ValueError: If the value is not a legal single segment.
    """
    if not value:
        raise ValueError(f"{kind} must be a non-empty topic segment")
    if "/" in value:
        raise ValueError(f"{kind} {value!r} must not contain '/'")
    if "+" in value or "#" in value:
        raise ValueError(f"{kind} {value!r} must not contain MQTT wildcards '+' or '#'")
    return value


def build_topic(
    owner_id: str,
    suffix: str,
    nested_id: Optional[str] = None,
    skip_prefixes: bool = False) -> str:
    """
    Build a full MQTT topic from an owner id and a suffix.

    Service/Node endpoints: `{owner_id}/{suffix}` e.g. `deviceWatcher/@/About`.
    Channel endpoints: `{owner_id}/{nested_id}/{suffix}` e.g. `deviceWatcher/cpuLoad/!/Stream`.
    Wildcard monitors pass skip_prefixes=True and use the suffix as-is (`+/@/About`).
    """
    if skip_prefixes:
        return suffix
    validate_segment(owner_id, "owner id")
    if nested_id is not None:
        validate_segment(nested_id, "channel id")
        return f"{owner_id}/{nested_id}/{suffix}"
    return f"{owner_id}/{suffix}"


def about_topic(owner_id: str) -> str:
    """The retained About topic of a client component."""
    return build_topic(owner_id, "@/About")
