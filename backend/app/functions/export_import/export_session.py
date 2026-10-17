from fastapi import HTTPException, status
import json
import logging
import os
import shutil
from pathlib import Path
from tempfile import mkdtemp
from datetime import datetime
from uuid import UUID, uuid4
from app.domain.store import store
from app.domain.models import Group, Role, Player, now_utc
from app.core.config import settings
from app.core.chat_store import chat_store
from app.functions.export_import.session_paths import saved_path, validate_session_tree

BASE_DIR = os.path.join(settings.backend_root_path, "data", "SavedSessions")
logger = logging.getLogger(__name__)


def _remove_export_directory(path: Path, parent: Path) -> None:
    # Only remove a work directory created for this export. Recheck containment
    # and links before recursive removal, including on Windows.
    if (path.resolve().parent != parent.resolve()
            or path.is_symlink() or path.is_junction()):
        raise ValueError("Export work directory escaped its parent")
    shutil.rmtree(path)


def staged_export(destination: Path, prepare, validate) -> None:
    """Publish a complete export, retaining the original on failure.

    Windows cannot rename a directory over a nonempty directory. Move the
    original aside first and restore it if promoting the prepared sibling
    fails. The caller holds the existing process-local lifecycle lock.
    """
    destination = Path(destination)
    parent = destination.parent
    if destination.exists() and not destination.is_dir():
        raise HTTPException(409, "Session destination is not a directory")
    validate_session_tree(destination)
    try:
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(mkdtemp(prefix=".session-export-", dir=parent))
    except PermissionError as error:
        raise HTTPException(403, "Can not create campaign/session export directory") from error
    backup = None
    try:
        prepare(staging)
        validate(staging)
        # Recheck before moving the original, after potentially lengthy copying.
        validate_session_tree(destination)
        if destination.exists():
            backup = parent / (".session-backup-" + uuid4().hex)
            if backup.exists():
                raise FileExistsError("Export backup destination already exists")
            os.rename(destination, backup)
        try:
            os.rename(staging, destination)
        except Exception:
            if backup is not None:
                try:
                    os.rename(backup, destination)
                except Exception as rollback_error:
                    # Never remove the original if Windows blocks rollback.
                    logger.exception("Export rollback failed; original retained at %s", backup)
                    raise HTTPException(
                        500, f"Export replacement failed; original session preserved at {backup}. "
                             "Restore that directory before retrying.",
                    ) from rollback_error
            raise
        if backup is not None:
            try:
                _remove_export_directory(backup, parent)
            except Exception:
                # Publication succeeded. A leftover backup is safe; do not
                # report a failed export after committing the new session.
                logger.warning("Export saved; unable to remove backup %s", backup, exc_info=True)
    finally:
        if staging.exists():
            try:
                _remove_export_directory(staging, parent)
            except Exception:
                logger.warning("Unable to remove export staging directory %s", staging, exc_info=True)

def export_group_to_json(folder_path: str) -> None:
    """
    Saves a list of Group objects (and their players) into a JSON file.
    """

    if len(store.group.players) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Can not save session, because currently no active"
                                                                f"player is still in the session")

    def serialize_group(group: Group) -> dict:
        return {
            "id": str(group.id),
            "max_size": group.max_size,
            "players": [p.to_dict() for p in group.players.values()],
        }

    data = serialize_group(store.group)

    try:
        file_path = os.path.join(folder_path, "group.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except PermissionError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Could not save group.json")



def export_settings_to_json(folder_path: str) -> None:
    """
    Export all fields of the settings-object to a JSON file.
    """
    data = {}

    # Include all Pydantic fields
    data.update(settings.model_dump())  # model_dump() returns a dict of all fields

    try:
        file_path = os.path.join(folder_path, "settings.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"Settings exported to {file_path}")
    except PermissionError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Could not save settings.json")

def copy_chroma_db(folder_path: str) -> None:
    """
    Copy Chroma into a fresh export directory; never delete an existing DB.
    """
    source_path = settings.chroma_db_path

    if not os.path.exists(source_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Source folder for DB does not exist: {source_path}")

    os.makedirs(folder_path, exist_ok=True)

    dest_folder_path = os.path.join(folder_path, "chroma_db")

    try:
        shutil.copytree(source_path, dest_folder_path)
        print(f"Copied 'chroma_db' to {dest_folder_path}")
    except PermissionError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Could not copy chroma_db folder: {source_path}")



# Not sure if this is wanted for all players, if they are kept seperately for each player. Would also e necessary to save the player uuid in the file or filename
# to know in the read in, which one belongs to which
async def export_chat_history_of_player(player_id: UUID, folder_path: str) -> None:
    """
    Exports the chat history of a given player to a TXT file.

    Args:
        player_id: The UUID of the player.
        folder_path: Directory where the chat file will be saved.
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


def get_folder_name(campaign_name: str, session_name: str) -> str:
    folder_path = str(saved_path(BASE_DIR, campaign_name, session_name))
    validate_session_tree(folder_path)
    os.makedirs(folder_path, exist_ok=True)

    return folder_path


def rename_folder(campaign_name: str, old_session_name: str, new_session_name: str) -> None:
    old_folder_path = saved_path(BASE_DIR, campaign_name, old_session_name)
    new_folder_path = saved_path(BASE_DIR, campaign_name, new_session_name)
    if new_folder_path.exists():
        raise HTTPException(409, "A session with the new name already exists")
    os.rename(old_folder_path, new_folder_path)
