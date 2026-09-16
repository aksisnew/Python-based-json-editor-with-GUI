import json
import os
import threading
from typing import Any, Dict, List, Tuple, Optional

import createFile

_READ_LOCKS: Dict[str, threading.RLock] = {}
_GLOBAL_LOCK = threading.RLock()


def _get_read_lock(filepath: str) -> threading.RLock:
    """Retrieves or creates a thread-safe lock for reading JSON files."""
    abs_path = os.path.abspath(filepath)
    with _GLOBAL_LOCK:
        if abs_path not in _READ_LOCKS:
            _READ_LOCKS[abs_path] = threading.RLock()
        return _READ_LOCKS[abs_path]


# -------------------------------------------------------------------
# Primary Key Detection APIs
# -------------------------------------------------------------------

COMMON_PK_CANDIDATES = ["id", "_id", "pk", "key", "uuid", "code"]


def detect_primary_key(json_data: Any) -> Optional[str]:
    """
    Analyzes JSON structure to auto-detect a primary key field name.
    Inspects dictionary keys or array element keys for common identifiers.
    """
    if isinstance(json_data, dict):
        for candidate in COMMON_PK_CANDIDATES:
            if candidate in json_data:
                return candidate
        # If no common candidate matched, return the first key if available
        keys = list(json_data.keys())
        return keys[0] if keys else None

    elif isinstance(json_data, list) and len(json_data) > 0:
        first_item = json_data[0]
        if isinstance(first_item, dict):
            for candidate in COMMON_PK_CANDIDATES:
                if candidate in first_item:
                    return candidate
            keys = list(first_item.keys())
            return keys[0] if keys else None

    return None


# -------------------------------------------------------------------
# File Reader & Parser
# -------------------------------------------------------------------

def load_json_file(rel_path: str) -> Tuple[Any, Optional[str]]:
    """
    Safely reads and parses a JSON file from the project directory scope.
    
    Returns:
        (parsed_json_data, primary_key_field_name)
    """
    abs_filepath = createFile._resolve_safe_path(rel_path)

    if not os.path.exists(abs_filepath):
        raise FileNotFoundError(f"File '{rel_path}' does not exist.")

    lock = _get_read_lock(abs_filepath)
    with lock:
        try:
            with open(abs_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                pk_field = detect_primary_key(data)
                return data, pk_field
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in file '{rel_path}': {e}")
        except Exception as e:
            raise IOError(f"Failed to read file '{rel_path}': {e}")


# -------------------------------------------------------------------
# Intermediate Tree Node Construction for GUI
# -------------------------------------------------------------------

def build_tree_nodes(data: Any, parent_key: str = "root") -> List[Dict[str, Any]]:
    """
    Recursively converts raw JSON objects/arrays into an intermediate 
    structured node list used by jsonguiedit.py to render text-box controls.
    
    Node Structure:
    {
        "key": str,
        "value": Any,
        "type": "string" | "number" | "boolean" | "null" | "object" | "array",
        "children": List[Node]
    }
    """
    nodes = []

    if isinstance(data, dict):
        for k, v in data.items():
            nodes.append(_parse_single_node(k, v))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            nodes.append(_parse_single_node(f"[{idx}]", item))
    else:
        nodes.append(_parse_single_node(parent_key, data))

    return nodes


def _parse_single_node(key: str, val: Any) -> Dict[str, Any]:
    """Classifies value types and constructs individual node representations."""
    if isinstance(val, dict):
        return {
            "key": key,
            "value": None,
            "type": "object",
            "children": build_tree_nodes(val, key)
        }
    elif isinstance(val, list):
        return {
            "key": key,
            "value": None,
            "type": "array",
            "children": build_tree_nodes(val, key)
        }
    elif isinstance(val, bool):
        return {
            "key": key,
            "value": val,
            "type": "boolean",
            "children": []
        }
    elif isinstance(val, (int, float)):
        return {
            "key": key,
            "value": val,
            "type": "number",
            "children": []
        }
    elif val is None:
        return {
            "key": key,
            "value": None,
            "type": "null",
            "children": []
        }
    else:
        return {
            "key": key,
            "value": str(val),
            "type": "string",
            "children": []
        }
