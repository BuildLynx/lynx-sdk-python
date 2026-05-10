"""
Recursive renderer that converts a Lynx payload schema dict into
a markdown indented bullet list (schema-viewer style).
"""

from typing import Any

CONSTRAINT_KEYS = (
    "default", "minimum", "maximum", "enum", "unit",
    "format", "minItems", "maxItems", "pattern",
)


def _format_type(type_value: Any) -> str:
    """Format a JSON schema type (string or list) into a display string."""
    if isinstance(type_value, list):
        return " | ".join(str(t) for t in type_value)
    return str(type_value)


def _format_constraint(key: str, value: Any) -> str:
    """Format a single constraint as an inline code badge."""
    if isinstance(value, list):
        display = ",".join(str(v) for v in value)
    elif isinstance(value, dict):
        display = "{}" if not value else str(value)
    else:
        display = str(value)
    return f"`{key}: {display}`"


def _render_property(
    name: str,
    prop: dict,
    indent: int,
    lines: list[str],
):
    """Render a single property and recurse into children."""
    prefix = "    " * indent + "- "
    type_str = _format_type(prop.get("type", ""))
    description = prop.get("description", "")

    line = f"{prefix}`{name}` **{type_str}**"
    if description:
        line += f" — {description}"

    constraints = []
    for key in CONSTRAINT_KEYS:
        if key in prop:
            constraints.append(_format_constraint(key, prop[key]))

    if constraints:
        line += "  "  # trailing double-space for markdown line break
        lines.append(line)
        badge_prefix = "    " * indent + "  "
        lines.append(badge_prefix + " ".join(constraints))
    else:
        lines.append(line)

    if prop.get("type") == "object" and "properties" in prop:
        _render_properties(prop["properties"], indent + 1, lines)

    if prop.get("type") == "array" and "items" in prop:
        _render_schema_node(prop["items"], indent + 1, lines)


def _render_properties(properties: dict, indent: int, lines: list[str]):
    """Render a dict of {name: prop_schema} entries."""
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        _render_property(name, prop, indent, lines)


def _render_schema_node(schema: dict, indent: int, lines: list[str]):
    """Render a schema node that may be an object, array, or properties dict."""
    if schema.get("type") == "array":
        prefix = "    " * indent + "- "
        lines.append(f"{prefix}`[]` **array**")
        if "items" in schema:
            _render_schema_node(schema["items"], indent + 1, lines)
        return

    if schema.get("type") == "object" and "properties" in schema:
        _render_properties(schema["properties"], indent, lines)
        return

    if "properties" in schema:
        _render_properties(schema["properties"], indent, lines)
        return


def render_schema(schema: dict) -> str:
    """
    Convert a Lynx payload schema dict into a markdown bullet list.

    Handles three schema shapes:
      - Flat properties dict (keys are property names with type/description)
      - Top-level type:"array" with items.properties (channel output envelope)
      - Nested objects with properties (e.g. @/About schema)

    Returns the rendered markdown string (without leading/trailing blank lines).
    """
    if not schema:
        return "*Empty payload*"

    lines: list[str] = []

    if "type" in schema:
        _render_schema_node(schema, indent=0, lines=lines)
    else:
        _render_properties(schema, indent=0, lines=lines)

    return "\n".join(lines) if lines else "*Empty payload*"
