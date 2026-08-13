"""
Helpers for nested dictionaries used by About merging and schema composition.

Generative AI was used in the Creation/Modification of this file.
"""

from typing import Dict
import collections.abc


def deep_merge(d1: Dict, d2: Dict, make_copy: bool = True) -> Dict:
    """
    Recursively merges dict2 into dict1.
    If a key exists in both and both values are dictionaries, they are merged.
    Otherwise, the value from dict2 overwrites the value in dict1.
    Args:
        d1: The first dictionary to merge.
        d2: The second dictionary to merge.
        make_copy: Whether to make a copy of the first dictionary before merging.
    Returns:
        A new dictionary with the merged contents.
    """
    if make_copy:
        merged = d1.copy()
    else:
        merged = d1

    for key, value in d2.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, collections.abc.Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value

    return merged
