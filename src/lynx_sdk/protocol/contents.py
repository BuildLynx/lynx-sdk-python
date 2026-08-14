"""
Lynx contents filter: trim a payload to the keys requested by a contents object.

Generative AI was used in the Creation/Modification of this file.
"""

from typing import Any, Dict, List
import xxhash
import orjson


def blank_payload_like(model_payload: Any, leaf_value: Any = None) -> Any:
    """
    Build a same-shaped payload with every leaf replaced by leaf_value.

    Used as a change-detection baseline for contents filtering, not as a test double.
    """
    if isinstance(model_payload, Dict):
        mock_payload = {}
        for key in model_payload.keys():
            if isinstance(model_payload[key], Dict):
                mock_payload[key] = blank_payload_like(model_payload[key])
            elif isinstance(model_payload[key], List):
                mock_payload[key] = [blank_payload_like(item) for item in model_payload[key]]
            else:
                mock_payload[key] = leaf_value
        return mock_payload
    elif isinstance(model_payload, List):
        return [blank_payload_like(item) for item in model_payload]
    else:
        return leaf_value


def trim_payload_by_contents(
    payload: Dict | Any,
    contents: Dict | List | bool | str = True,
    old_payload: Dict | Any | None = None) -> Any:
    """
    Recursively build a JSON dict by trimming a superset dict by a dict of keys to contents.
    """
    if old_payload is None:
        old_payload = blank_payload_like(payload)
    try:
        if contents is True:
            return payload
        elif contents is False:
            if old_payload == payload:
                return None
            else:
                return payload
        elif isinstance(contents, str):
            xxh32_hash_str = xxhash.xxh32(orjson.dumps(payload)).hexdigest()
            if xxh32_hash_str == contents:
                return None
            else:
                if isinstance(payload, Dict):
                    return {k: xxhash.xxh32(orjson.dumps(v)).hexdigest() for k, v in payload.items()}
                else:
                    return xxh32_hash_str
        elif isinstance(contents, List) and len(contents) > 0:
            if isinstance(payload, List) and len(payload) > 0:
                new_payload = []
                for idx in range(len(payload)):
                    returned_value = trim_payload_by_contents(payload[idx], contents[0], old_payload[idx])
                    if returned_value is not None:
                        new_payload.append(returned_value)
                return new_payload
            else:
                return PayloadBuildingError(f"Invalid payload type: {type(payload)}. Expected List.")
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


class PayloadBuildingError(Exception):
    """
    Exception raised when a payload building error occurs.
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
