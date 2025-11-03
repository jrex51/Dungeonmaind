import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime
from uuid import UUID
from app.domain.store import store
from app.domain.models import Group, Role, Player, now_utc
from app.core.config import settings


def load_groups_from_json(file_path: str) -> None:
    """
    Loads group and player data from a JSON file into the store.
    If the file does not exist, does nothing.
    """

    if not file_path.exists():
        print(f"No saved group data found at {file_path}")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Deserialize players
        players = {}
        for p in data.get("players", []):
            player = Player(
                id=UUID(p["id"]),
                name=p["name"],
                role=Role(p["role"]),
                created_at=datetime.fromisoformat(p["created_at"]),
                #last_seen_at=datetime.fromisoformat(p["last_seen_at"]),
                last_seen_at=now_utc(),
            )
            players[player.id] = player

        # Deserialize group
        group = Group(
            id=UUID(data["id"]),
            max_size=data["max_size"],
            players=players
        )

        # Update global store
        store.group = group

        print(f"Loaded group data from {file_path} with {len(players)} players")

    except Exception as e:
        print(f"Failed to load group data: {e}")

    # Still needs the logic to set the players in game


def load_settings_from_json(file_path: str) -> None:
    """
    Reads settings properties from a JSON file and updates the settings-object.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key, value in data.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
        else:
            print(f"Warning: settings has no attribute '{key}', skipping.")


# Have first to test if this works
def load_settings_from_json2(file_path: str) -> None:
    """
    Loads settings from a JSON file into the global settings-object.
    Missing or invalid keys fall back to the default values defined in Settings.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
    except FileNotFoundError:
        print(f"Settings file {file_path} not found. Using defaults.")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}. Using defaults.")
        return

    # Iterate over fields of Settings and update if present in JSON
    for field_name, field_info in settings.__fields__.items():
        if field_name in data:
            value = data[field_name]
            expected_type = field_info.outer_type_
            # Validate type
            if isinstance(value, expected_type):
                setattr(settings, field_name, value)
            else:
                print(f"Warning: '{field_name}' has invalid type {type(value).__name__}, expected {expected_type.__name__}. Using default.")


def replace_chroma_db(saved_sessions_path: str, data_path: str) -> None:
    """
    Replace the current chroma_db in data_path with the one from the saved session.

    Args:
        saved_sessions_path: Path to the SavedSessions folder.
        session_name: Name of the session folder inside SavedSessions.
        data_path: Path to the data folder where the active chroma_db lives.
    """
    session_db_path = os.path.join(saved_sessions_path, "chroma_db")
    target_db_path = os.path.join(data_path, "chroma_db")

    if not os.path.isdir(session_db_path):
        raise FileNotFoundError(f"No chroma_db found in saved session: {session_db_path}")

    if not os.path.isdir(data_path):
        raise FileNotFoundError(f"Data path does not exist: {data_path}")

    # Remove existing chroma_db in data folder
    if os.path.exists(target_db_path):
        shutil.rmtree(target_db_path)
        print(f"Removed old chroma_db at {target_db_path}")

    # --- Copy the saved chroma_db into data folder ---
    shutil.copytree(session_db_path, target_db_path)
    print(f"Restored chroma_db from {session_db_path} to {target_db_path}")

def read_chat_history(file_path: str) -> List[Dict[str, str]]:
    """
    Reads a chat history TXT file and returns a list of messages.

    Args:
        file_path: Path to the chat TXT file.

    Returns:
        List of messages, each a dict with keys 'role' and 'content'.
    """
    messages = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("[") and "]" in line:
                role_end = line.index("]")
                role = line[1:role_end].strip()
                content = line[role_end + 1 :].strip()
                messages.append({"role": role, "content": content})
            else:
                # fallback if line doesn't match expected format
                messages.append({"role": "unknown", "content": line})

    return messages
