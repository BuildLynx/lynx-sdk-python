"""
Canonical JSON Schema representation for Lynx endpoint payloads.

Generative AI was used in the Creation/Modification of this file.

Lynx has exactly one canonical representation for a payload schema: a complete
JSON Schema (Draft 7) object carrying a "type" keyword. That is the form stored
on an Endpoint, the form used for validation, and the form published in About.
Protocol A2.1 section 4.6 requires the advertised schema to be the enforced one,
so there must be no second representation that only exists at validation time.

Authoring a bare properties map is still convenient, so `normalize_payload_schema`
accepts one -- but it must be passed explicitly as `payload_properties`, never guessed at.
"""

from typing import Dict, Optional, TYPE_CHECKING
import jsonschema

if TYPE_CHECKING:
    from jsonschema.protocols import Validator


DRAFT_07_URI = "http://json-schema.org/draft-07/schema#"


def build_object_schema(
    properties: Dict,
    additional_properties: bool = False,
    jsonschema_version: str = DRAFT_07_URI) -> Dict:
    """
    Wrap a map of {property name: subschema} into a complete object schema.

    This performs no detection: the caller is stating that `properties` is a properties
    map. An empty map yields a schema accepting only the empty object, which is how
    commands that take no parameters (such as !/Stop) are expressed.

    Args:
        properties: Map of property name to subschema.
        additional_properties: Whether unrecognized keys are accepted.
        jsonschema_version: Value for the $schema keyword.

    Returns:
        A complete Draft-7 object schema.
    """
    return {
        "$schema": jsonschema_version,
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }


def normalize_payload_schema(
    payload_schema: Optional[Dict] = None,
    payload_properties: Optional[Dict] = None,
    additional_properties: bool = False) -> Optional[Dict]:
    """
    Produce and validate the canonical form of an endpoint's payload schema.

    Exactly one of the two schema arguments may be supplied:

    - `payload_properties` is a bare map of property names to subschemas, and is
      wrapped into an object schema.
    - `payload_schema` is already complete and must carry a "type" keyword. Its
      `additionalProperties` is filled in from the argument when absent, and is
      never overwritten when the schema already states it.

    Args:
        payload_schema: A complete Draft-7 schema object.
        payload_properties: A bare properties map to be wrapped.
        additional_properties: Whether unrecognized keys are accepted. Applied only
            to object schemas, the keyword being meaningless elsewhere.

    Returns:
        The canonical schema, or None when neither schema argument is supplied.

    Raises:
        SchemaDefinitionError: If both schema arguments are supplied, if
            `payload_schema` lacks a "type" keyword, or if the result is not a
            valid Draft-7 schema.
    """
    if payload_schema is not None and payload_properties is not None:
        raise SchemaDefinitionError(
            "Supply payload_schema or payload_properties, not both. payload_schema is a "
            "complete Draft-7 schema; payload_properties is a bare map of property names "
            "to subschemas."
        )

    if payload_properties is not None:
        schema = build_object_schema(payload_properties, additional_properties=additional_properties)
    elif payload_schema is not None:
        if "type" not in payload_schema:
            raise SchemaDefinitionError(
                "payload_schema must be a complete Draft-7 schema carrying a \"type\" keyword. "
                "A bare map of property names is read by a validator as the empty schema, which "
                "accepts any payload. Pass it as payload_properties instead."
            )
        schema = dict(payload_schema)
        schema.setdefault("$schema", DRAFT_07_URI)
        if schema.get("type") == "object":
            schema.setdefault("additionalProperties", additional_properties)
    else:
        return None

    validate_payload_schema(schema)
    return schema


def validate_payload_schema(json_schema: Dict) -> bool:
    """
    Check that a payload schema is a valid Draft-7 schema.

    Args:
        json_schema: The schema to check, already in canonical form.

    Returns:
        True if the schema is valid.

    Raises:
        SchemaDefinitionError: If the schema is invalid, wrapping the underlying
            jsonschema SchemaError message.
    """
    try:
        jsonschema.Draft7Validator.check_schema(json_schema)
    except jsonschema.exceptions.SchemaError as e:
        raise SchemaDefinitionError(f"Invalid JSON schema: {e.message}") from e
    return True


def validate_json_object(
    json_object: Dict,
    json_schema: Dict,
    validator: Optional["Validator"] = None) -> None:
    """
    Validate a JSON object against a canonical JSON schema.

    The schema is used exactly as given. Normalization happens once, when an Endpoint
    is built, so the schema enforced here is the one published in About.

    Args:
        json_object: The payload to validate.
        json_schema: A canonical Draft-7 schema.
        validator: Optional pre-built validator.

    Raises:
        jsonschema.exceptions.ValidationError: If the object does not match the schema.
    """
    if validator is None:
        validator = jsonschema.Draft7Validator(json_schema)
    validator.validate(json_object)


class SchemaDefinitionError(Exception):
    """
    Raised when a payload schema is malformed or ambiguously declared.

    This is a programming error in how a component was defined, not a runtime data
    error, so it is raised at construction time rather than logged. A component whose
    advertised schema is invalid cannot honor A2.1 section 4.6, and failing early
    surfaces the problem when `lynx docs` runs rather than after deployment.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
