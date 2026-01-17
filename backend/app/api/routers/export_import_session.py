from fastapi import APIRouter, HTTPException, status, Request
import os
from pathlib import Path
from typing import Dict, List
from app.functions.export_import.export_session import (export_group_to_json, export_settings_to_json, copy_chroma_db,
                                                        export_chat_history_of_player, get_folder_name, rename_folder)
from app.functions.export_import.import_session import (load_groups_from_json, load_settings_from_json,
                                                        read_chat_history, replace_chroma_db)
from app.functions.export_import.delete_session import delete_folder
from app.base_models.export_import_models import (ExportRequest, Sessions, ImportRequest, Campaigns, DeleteRequest,
                                                  RenameRequest)
from app.core.config import settings
from app.base_models.schemas import PlayerOut
from app.core.bus import bus
from app.domain.store import store
from app.api.mappers.player_mapper import player_to_out



router = APIRouter()

# Have to add error handling and finish the import stuff

SAVED_SESSIONS_DIR = os.path.join(settings.backend_root_path, "data", "SavedSessions")
DATA_DIR = os.path.join(settings.backend_root_path, "data")


@router.post("/export")
def export_session(req: ExportRequest) -> None:
    campaign_folder_path = os.path.join(SAVED_SESSIONS_DIR, req.campaign_name)
    try:
        if not os.path.exists(campaign_folder_path):
            os.makedirs(campaign_folder_path, exist_ok=True)
            print(f"Created campaign folder: {campaign_folder_path}")
    except PermissionError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Can not create campaign folder at "
                                                              f"{campaign_folder_path}")
    folder_path = get_folder_name(req.campaign_name, req.session_name)
    export_group_to_json(folder_path)
    export_settings_to_json(folder_path)
    copy_chroma_db(folder_path) # What is if at this point not all transcriptions are calculated?


@router.post("/import")
async def import_session(req: ImportRequest, request: Request) -> PlayerOut:
    folder_path = os.path.join(SAVED_SESSIONS_DIR, req.campaign_name, req.session_name)
    if not os.path.isdir(folder_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Session folder '{req.session_name}' does not exist.")
    file_path_settings = os.path.join(folder_path, "settings.json")
    load_settings_from_json(file_path_settings)
    file_path_groups = os.path.join(folder_path, "group.json")
    leader = load_groups_from_json(file_path_groups)

    replace_chroma_db(folder_path, DATA_DIR)

    # Maybe the publishing has to be player by player, so that actually only those players are shown, which actually
    # newly logged in the loaded session
    await bus.publish({
        "type": "session_imported",
        "players": [p.name for p in store.group.players.values()],
    })

    return player_to_out(leader, request)


@router.get("/getSessions", response_model=Sessions)
def get_sessions() -> None:
    base_path = Path(SAVED_SESSIONS_DIR)

    if not base_path.exists() or not base_path.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Invalid path: {SAVED_SESSIONS_DIR}")

    folder_names = [
        item.name for item in base_path.iterdir() if item.is_dir()
    ]

    return Sessions(folders=folder_names)


@router.get("/getCampaigns", response_model=Campaigns)
def get_campaigns():
    base_path = Path(SAVED_SESSIONS_DIR)

    if not base_path.exists() or not base_path.is_dir():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Invalid path: {SAVED_SESSIONS_DIR}"
        )

    campaigns: Dict[str, Sessions] = {}

    for campaign_dir in base_path.iterdir():
        if campaign_dir.is_dir():
            # List session subfolders inside each campaign
            session_names = [
                s.name for s in campaign_dir.iterdir() if s.is_dir()
            ]

            campaigns[campaign_dir.name] = Sessions(folders=session_names)

    return Campaigns(campaigns=campaigns)


@router.post("/deleteCampaignsOrSessions")
def get_campaigns(req: DeleteRequest):
    delete_folder(req.campaign_or_session_name)


@router.post("/renameSession")
def get_campaigns(req: RenameRequest):
    rename_folder(req.campaign_name, req.old_session_name, req.new_session_name)
