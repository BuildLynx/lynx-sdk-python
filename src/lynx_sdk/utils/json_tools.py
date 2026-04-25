"""
This module provides tools for validating JSON objects and JSON schemas.
"""



# === IMPORTS ===

# -stdlib Imports-
import copy

# -Lynx Imports-

# -External Imports-
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import jsonschema

if TYPE_CHECKING:
    from jsonschema.protocols import Validator



# === CONSTANTS ===



# === GLOBALS VARIABLES ===



# === FUNCTIONS ===
def make_mock_payload(model_payload: Dict) -> Dict:
    """
    Make a mock payload from a model payload.
    """
    if isinstance(model_payload, Dict):
        mock_payload = {}
        for key in model_payload.keys():
            if isinstance(model_payload[key], Dict):
                mock_payload[key] = make_mock_payload(model_payload[key])
            elif isinstance(model_payload[key], List):
                mock_payload[key] = [make_mock_payload(item) for item in model_payload[key]]
            else:
                mock_payload[key] = None
        return mock_payload
    elif isinstance(model_payload, List):
        return [make_mock_payload(item) for item in model_payload]
    else:
        return None


# -JSON Payload Tools-
def trim_payload_by_contents(
    payload: Dict,
    contents: Dict | List | bool = True,
    old_payload: Dict | None = None) -> Any:
    """
    Recursively build a JSON dict by trimming a superset dict by a dict of keys to contents. 
    """
    if old_payload is None:
        old_payload = make_mock_payload(payload)
    try:
        # -Boolean cases-
        if contents is True:
            return payload
        elif contents is False:
            if old_payload == payload:
                return None
            else:
                return payload
        # -List case-
        elif isinstance(contents, List) and len(contents) > 0: # Have to dig one level deeper in payload if it's an array
            if isinstance(payload, List) and len(payload) > 0:
                new_payload = []
                for idx in range(len(payload)):
                    returned_value = trim_payload_by_contents(payload[idx], contents[0], old_payload[idx])
                    if returned_value is not None:
                        new_payload.append(returned_value)
                return new_payload
            else:
                return PayloadBuildingError(f"Invalid payload type: {type(payload)}. Expected List.")
        # -Dict case-
        elif isinstance(contents, Dict):
            if isinstance(payload, Dict) and len(payload) > 0:
                new_payload = {}
                for key in contents.keys():
                    returned_value = trim_payload_by_contents(payload[key], contents[key], old_payload[key])
                    if returned_value is not None:
                        new_payload[key] = returned_value
                return new_payload
            else:
                return PayloadBuildingError(f"Invalid payload type: {type(payload)}. Expected Dict.")
        else:
            raise PayloadBuildingError(f"Invalid type in \"contents\" object: {type(contents)}. Expected Dict, List, or bool.")
    except KeyError as e:
        raise PayloadBuildingError(f"Key \"{e}\" in contents not found in data.")


# -JSON Schema Tools-
def generate_full_data_schema(
    output_data_schema: Optional[Dict]=None,
    additional_properties: bool = False,
    jsonschema_version: str = "http://json-schema.org/draft-07/schema#") -> Optional[Dict]:
    """
    If the provided "schema" is not yet a real JSON schema object that has a "type" key, 
    this function will wrap it in an object with a "type" key and a "properties" key.
    """
    if output_data_schema is None:
        return None
    if "type" in output_data_schema:
        return output_data_schema
    else:
        return {
            "$schema": jsonschema_version,
            "type": "object",
            "properties": output_data_schema,
            "additionalProperties": additional_properties
        }


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
    validator: Optional["Validator"] = None
    ) -> bool:
    """
    Validate a JSON object against a JSON schema. By default, it uses the Draft 7 validator.
    Throws a jsonschema.exceptions.ValidationError if the JSON object does not match the schema.
    """
    json_schema = generate_full_data_schema(json_schema)
    
    # print(f"-----------------------:\n{json_object}\n{json_schema}\n")
    if validator is None:
        validator = jsonschema.Draft7Validator(json_schema)
    validator.validate(json_object)


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
