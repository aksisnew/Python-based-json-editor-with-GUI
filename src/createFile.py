import os
import re
import shutil
import json
import threading
from typing import List, Dict, Any, Union

# Lock authority strictly to the directory where the project is booted
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

_FILE_LOCKS: Dict[str, threading.RLock] = {}
_GLOBAL_LOCK = threading.RLock()


def _get_path_lock(target_path: str) -> threading.RLock:
    """Retrieves or creates a thread-safe lock for a specific path."""
    abs_path = os.path.abspath(target_path)
    with _GLOBAL_LOCK:
        if abs_path not in _FILE_LOCKS:
            _FILE_LOCKS[abs_path] = threading.RLock()
        return _FILE_LOCKS[abs_path]


def _resolve_safe_path(relative_or_abs_path: str) -> str:
    """
    Enforces the boot-directory boundary.
    Prevents path traversal attacks (e.g. '../') outside the project root directory.
    """
    if not relative_or_abs_path:
        return PROJECT_ROOT

    # Standardize path joins
    clean_path = relative_or_abs_path.strip().lstrip('/\\')
    full_path = os.path.abspath(os.path.join(PROJECT_ROOT, clean_path))

    # Path traversal check
    if not full_path.startswith(PROJECT_ROOT):
        raise PermissionError("Access denied: File operations restricted to the project root directory.")

    return full_path


def _sanitize_name(name: str) -> str:
    """Removes invalid filename characters."""
    clean_name = name.strip()
    return re.sub(r'[\\/:*?"<>|]', '', clean_name)


# -------------------------------------------------------------------
# Sidebar Explorer / Directory Tree APIs
# -------------------------------------------------------------------

def list_directory_contents(rel_path: str = "") -> List[Dict[str, Any]]:
    """
    Recursively scans and lists files and folders within the project root.
    Returns a tree structure suitable for rendering in the GUI sidebar.
    """
    target_dir = _resolve_safe_path(rel_path)

    if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
        return []

    tree = []
    try:
        entries = sorted(os.scandir(target_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in entries:
            # Exclude hidden files, python bytecode, and temporary files
            if entry.name.startswith('.') or entry.name == '__pycache__' or entry.name.endswith('.tmp'):
                continue

            rel_item_path = os.path.relpath(entry.path, PROJECT_ROOT)

            if entry.is_dir():
                tree.append({
                    "name": entry.name,
                    "rel_path": rel_item_path,
                    "type": "folder",
                    "children": list_directory_contents(rel_item_path)
                })
            elif entry.is_file() and entry.name.lower().endswith('.json'):
                tree.append({
                    "name": entry.name,
                    "rel_path": rel_item_path,
                    "type": "file"
                })
        return tree
    except OSError:
        return []


# -------------------------------------------------------------------
# File & Folder Creation APIs
# -------------------------------------------------------------------

def create_file(file_name: str, parent_folder: str = "") -> str:
    """
    Creates a new JSON file in parent_folder (or root if parent_folder is empty).
    Initializes the file with an empty JSON object `{}` atomically using exclusive creation mode ('x').
    """
    sanitized_name = _sanitize_name(file_name)
    if not sanitized_name.lower().endswith('.json'):
        sanitized_name += '.json'

    parent_path = _resolve_safe_path(parent_folder)
    target_filepath = os.path.join(parent_path, sanitized_name)
    _resolve_safe_path(target_filepath)  # Boundary validation

    lock = _get_path_lock(target_filepath)
    with lock:
        if os.path.exists(target_filepath):
            raise FileExistsError(f"File '{sanitized_name}' already exists.")

        try:
            with open(target_filepath, 'x', encoding='utf-8') as f:
                json.dump({}, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            return os.path.relpath(target_filepath, PROJECT_ROOT)
        except Exception as e:
            if os.path.exists(target_filepath):
                try:
                    os.remove(target_filepath)
                except OSError:
                    pass
            raise IOError(f"Failed to create file '{sanitized_name}': {e}")


def create_folder(folder_name: str, parent_folder: str = "") -> str:
    """Creates a new subfolder within the project root scope."""
    sanitized_name = _sanitize_name(folder_name)
    if not sanitized_name:
        raise ValueError("Folder name cannot be empty.")

    parent_path = _resolve_safe_path(parent_folder)
    target_folderpath = os.path.join(parent_path, sanitized_name)
    _resolve_safe_path(target_folderpath)

    lock = _get_path_lock(target_folderpath)
    with lock:
        if os.path.exists(target_folderpath):
            raise FileExistsError(f"Folder '{sanitized_name}' already exists.")

        try:
            os.makedirs(target_folderpath, exist_ok=True)
            return os.path.relpath(target_folderpath, PROJECT_ROOT)
        except Exception as e:
            raise IOError(f"Failed to create folder '{sanitized_name}': {e}")


# -------------------------------------------------------------------
# File & Folder Operations (Rename, Delete, Cut/Copy/Paste)
# -------------------------------------------------------------------

def rename_item(rel_path: str, new_name: str) -> str:
    """Renames a file or folder safely within the project scope."""
    old_path = _resolve_safe_path(rel_path)
    if not os.path.exists(old_path):
        raise FileNotFoundError("Target file or folder does not exist.")

    sanitized_name = _sanitize_name(new_name)
    if os.path.isfile(old_path) and not sanitized_name.lower().endswith('.json'):
        sanitized_name += '.json'

    parent_dir = os.path.dirname(old_path)
    new_path = os.path.join(parent_dir, sanitized_name)
    _resolve_safe_path(new_path)

    if os.path.exists(new_path) and old_path.lower() != new_path.lower():
        raise FileExistsError(f"An item named '{sanitized_name}' already exists in this folder.")

    lock = _get_path_lock(old_path)
    with lock:
        try:
            os.rename(old_path, new_path)
            return os.path.relpath(new_path, PROJECT_ROOT)
        except OSError:
            # Fallback for Windows file locks
            if os.path.isfile(old_path):
                shutil.copy2(old_path, new_path)
                os.remove(old_path)
                return os.path.relpath(new_path, PROJECT_ROOT)
            raise IOError(f"Could not rename '{rel_path}' to '{new_name}'.")


def delete_item(rel_path: str) -> None:
    """Deletes a file or directory recursively."""
    target_path = _resolve_safe_path(rel_path)
    if not os.path.exists(target_path):
        raise FileNotFoundError("Target does not exist.")

    if target_path == PROJECT_ROOT:
        raise PermissionError("Cannot delete the root project directory.")

    lock = _get_path_lock(target_path)
    with lock:
        try:
            if os.path.isdir(target_path):
                shutil.rmtree(target_path)
            else:
                os.remove(target_path)
        except Exception as e:
            raise IOError(f"Failed to delete '{rel_path}': {e}")


def clipboard_operation(source_rel_path: str, target_folder_rel_path: str, action: str = "copy") -> str:
    """
    Handles Cut/Copy/Paste operations across folders in the project directory.
    action: "copy" or "cut"
    """
    src_path = _resolve_safe_path(source_rel_path)
    dest_dir = _resolve_safe_path(target_folder_rel_path)

    if not os.path.exists(src_path):
        raise FileNotFoundError("Source item does not exist.")
    if not os.path.isdir(dest_dir):
        raise NotADirectoryError("Destination must be a valid directory.")

    item_name = os.path.basename(src_path)
    dest_path = os.path.join(dest_dir, item_name)
    _resolve_safe_path(dest_path)

    lock = _get_path_lock(src_path)
    with lock:
        try:
            if action == "copy":
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dest_path)
            elif action == "cut":
                shutil.move(src_path, dest_path)
            else:
                raise ValueError("Invalid action. Must be 'copy' or 'cut'.")

            return os.path.relpath(dest_path, PROJECT_ROOT)
        except Exception as e:
            raise IOError(f"Failed to execute {action} operation: {e}")
