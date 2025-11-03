from fastapi import APIRouter, HTTPException, status
import os
from pathlib import Path
from typing import List
from app.functions.export_import.export_session import export_group_to_json, export_settings_to_json, copy_chroma_db, export_chat_history_of_player, get_folder_name
from app.functions.export_import.import_session import load_groups_from_json, load_settings_from_json, read_chat_history, replace_chroma_db
from app.base_models.export_import_models import ExportRequest, Sessions, ImportRequest
from app.core.config import settings


router = APIRouter()

# Have to add error handling and finish the import stuff

SAVED_SESSIONS_DIR = os.path.join(settings.backend_root_path, "data", "SavedSessions")
DATA_DIR = os.path.join(settings.backend_root_path, "data")


@router.post("/export")
def export_session(req: ExportRequest) -> None:
    folder_path = get_folder_name(req.session_name)
    export_group_to_json(folder_path)
    export_settings_to_json(folder_path)
    copy_chroma_db(folder_path) # What is if at this point not all transcriptions are calculated?
    # Save Chat-History
    # Save Health characteristics etc.



@router.post("/import")
def import_session(req: ImportRequest) -> bool:
    folder_path = os.path.join(SAVED_SESSIONS_DIR, req.session_name)
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Session folder '{req.session_name}' does not exist.")
    file_path_settings = os.path.join(folder_path, "settings.json")
    load_settings_from_json(file_path_settings)
    file_path_groups = os.path.join(folder_path, "group.json")
    #load_groups_from_json(file_path_groups) # First we need the possibility for the players to re-log in as the saved players
    replace_chroma_db(folder_path, DATA_DIR)

    return True

@router.get("/getSessions")
def get_sessions() -> None:
    base_path = Path(SAVED_SESSIONS_DIR)

    if not base_path.exists() or not base_path.is_dir():
        raise ValueError(f"Invalid path: {SAVED_SESSIONS_DIR}")

    folder_names = [
        item.name for item in base_path.iterdir() if item.is_dir()
    ]

    return Sessions(folders=folder_names)


