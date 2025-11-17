import json
import os
import shutil
from datetime import datetime
from uuid import UUID
from app.domain.store import store
from app.domain.models import Group, Role, Player, now_utc
from app.core.config import settings
from app.core.chat_store import chat_store

BASE_DIR = os.path.join(settings.backend_root_path, "data", "SavedSessions")

def export_group_to_json(folder_path: str) -> None:
    """
    Saves a list of Group objects (and their players) into a JSON file.
    """
    def serialize_group(group: Group) -> dict:
        return {
            "id": str(group.id),
            "max_size": group.max_size,
            "players": [p.to_dict() for p in group.players.values()],
        }

    data = serialize_group(store.group)

    file_path = os.path.join(folder_path, "group.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def export_settings_to_json(folder_path: str) -> None:
    """
    Export all fields of the settings-object to a JSON file.
    """
    data = {}

    # Include all Pydantic fields
    data.update(settings.model_dump())  # model_dump() returns a dict of all fields

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


def get_folder_name(session_name: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{session_name}_{timestamp}"
    folder_path = os.path.join(BASE_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    return folder_path
