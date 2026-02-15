"""
This module provides tools for validating JSON objects and JSON schemas.
"""



# === IMPORTS ===

# -stdlib Imports-

# -Lynx Imports-

# -External Imports-
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import jsonschema

if TYPE_CHECKING:
    from jsonschema.protocols import Validator



# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===

# -JSON Payload Tools-
def trim_payload_by_include(
    payload: Dict,
    include: Dict | List | bool = True) -> Any:
    """
    Recursively build a JSON dict by trimming a superset dict by a dict of keys to include.
    """
    try:
        # -Boolean cases-
        if include is True:
            return payload
        elif include is False:
            return None
        # -List case-
        elif isinstance(include, List) and len(include) > 0: # Have to dig one level deeper in payload if it's an array
            if isinstance(payload, List) and len(payload) > 0:
                return [trim_payload_by_include(item, include[0]) for item in payload]
            else:
                return PayloadBuildingError(f"Invalid payload type: {type(payload)}. Expected List.")
        # -Dict case-
        elif isinstance(include, Dict):
            if isinstance(payload, Dict) and len(payload) > 0:
                return {key: trim_payload_by_include(payload[key], include[key]) for key in include.keys()}
            else:
                return PayloadBuildingError(f"Invalid payload type: {type(payload)}. Expected Dict.")
        else:
            raise PayloadBuildingError(f"Invalid type in \"Include\" object: {type(include)}. Expected Dict, List, or bool.")
    except KeyError as e:
        raise PayloadBuildingError(f"Error building payload: {e}")


# -JSON Schema Tools-
def wrap_json_in_object(
    json_dict: Dict
    ) -> Dict:
    """
    Detects if provided json_dict is a JSON schema object (by looking for the type key). 
    If it is, returns it. If it is not, wraps it in an object. 
    """
    if "type" in json_dict:
        return json_dict
    else:
        return {
            "type": "object",
            "properties": json_dict
        }

    
def validate_json_object(
    json_object: Dict,
    json_schema: Dict,
    validator: Optional["Validator"] = None,
    additional_properties: bool = False
    ) -> bool:
    """
    Validate a JSON object against a JSON schema. By default, it uses the Draft 7 validator.
    Throws a jsonschema.exceptions.ValidationError if the JSON object does not match the schema.
    """
    json_object = wrap_json_in_object(json_object)
    json_schema = wrap_json_in_object(json_schema)
    if validator is None:
        validator = jsonschema.Draft7Validator(json_schema)
    validator.validate(json_object, additional_properties=additional_properties)
    return True


def validate_json_schema(
    json_schema: Dict, 
    validator: Optional["Validator"] = None
    ) -> bool:
    """
    Validate a JSON schema. By default, it uses the Draft 7 validator.
    Throws a jsonschema.exceptions.SchemaError if the JSON schema is invalid.
    """
    json_schema = wrap_json_in_object(json_schema)
    if validator is None:
        validator = jsonschema.Draft7Validator(json_schema)
    validator.check_schema(json_schema)
    return True




#  === CLASSES ===

class PayloadBuildingError(Exception):
    """
    Exception raised when a payload building error occurs.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)



# === MAIN LOOP ===
