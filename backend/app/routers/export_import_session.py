import json
from fastapi import APIRouter, HTTPException, status
from pathlib import Path
from typing import Any, Dict, List
import os
import shutil
from datetime import datetime
from uuid import UUID
from app.domain.store import store
from app.domain.models import Group, Role, Player, now_utc
from app.core.config import settings
from app.core.chat_store import chat_store


router = APIRouter()

# Have to add error handling and finish the import stuff

@router.get("/export")
def export_session() -> None:
    folder_path = get_folder_name()
    export_group_to_json(folder_path)
    export_settings_to_json(folder_path)
    copy_chroma_db(folder_path) # What is if at this point not all transcriptions are calculated?
    # Save Chat-History


def export_group_to_json(folder_path: str) -> None:
    """
    Saves a list of Group objects (and their players) into a JSON file.
    """
    def serialize_group(group: Group) -> dict:
        return {
            "id": str(group.id),
            "max_size": group.max_size,
            "players": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "role": p.role.value,
                    "created_at": p.created_at.isoformat(),
                    "last_seen_at": p.last_seen_at.isoformat(),
                }
                for p in group.players.values()
            ],
        }

    data = serialize_group(store.group)

    file_path = os.path.join(folder_path, "group.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def export_settings_to_json(folder_path: str) -> None:
    """
    Export all fields of the `settings` object to a JSON file.
    """
    data = {}

    # Include all Pydantic fields
    data.update(settings.model_dump())  # model_dump() returns a dict of all fields

    properties = ["chroma_db_path"]
    for prop in properties:
        data[prop] = getattr(settings, prop)

    file_path = os.path.join(folder_path, "settings.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(f"Settings exported to {file_path}")


def copy_chroma_db(folder_path: str) -> None:
    """
    Copies the 'chroma_db' folder (including all its files)
    into the specified destination path.
    """
    source_path = settings.chroma_db_path

    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source folder does not exist: {source_path}")

    os.makedirs(folder_path, exist_ok=True)

    dest_folder_path = os.path.join(folder_path, "chroma_db")

    if os.path.exists(dest_folder_path):
        shutil.rmtree(dest_folder_path)

    shutil.copytree(source_path, dest_folder_path)
    print(f"Copied 'chroma_db' to {dest_folder_path}")


# Not sure if this is wanted for all players, if they are kept seperately for each player. Would also e necessary to save the player uuid in the file or filename
# to know in the read in, which one belongs to which
async def export_chat_history_of_player(player_id: UUID, folder_path: str) -> None:
    """
    Exports the chat history of a given player to a TXT file.

    Args:
        player_id: The UUID of the player.
        output_dir: Directory where the chat file will be saved.
    """

    history = await chat_store.history(player_id)

    if not history:
        raise ValueError(f"No chat history found for player {player_id}")

    file_path = os.path.join(folder_path, f"chat_history_{player_id}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            f.write(f"[{role}] {content}\n")


def get_folder_name() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"Session_{timestamp}"
    folder_path = os.path.join("data/SavedSessions", folder_name)
    os.makedirs(folder_path, exist_ok=True)

    return folder_path


@router.get("/import")
def import_session() -> None:
    print("Not finished yet")


def load_groups_from_json(relative_path: str = "data/groups.json") -> None:
    """
    Loads group and player data from a JSON file into the in-memory store.
    If the file does not exist, does nothing.
    """
    base_dir = Path(__file__).resolve().parent
    file_path = base_dir / relative_path

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
    Reads settings properties from a JSON file and updates the `settings` object.
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
    Loads settings from a JSON file into the global `settings` object.
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
