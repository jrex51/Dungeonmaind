from fastapi import APIRouter, HTTPException, status, Request
import os
import asyncio
from pathlib import Path
from typing import Dict, List
from app.functions.export_import.export_session import (export_group_to_json, export_settings_to_json, copy_chroma_db,
                                                        export_chat_history_of_player, staged_export, rename_folder)
from app.functions.export_import.import_session import (load_groups_from_json, load_settings_from_json,
                                                        read_group_from_json, read_settings_from_json,
                                                        read_chat_history, replace_chroma_db)
from app.functions.export_import.delete_session import delete_folder
from app.base_models.export_import_models import (ExportRequest, Sessions, ImportRequest, Campaigns, DeleteRequest,
                                                  RenameRequest)
from app.core.config import settings
from app.base_models.schemas import PlayerOut
from app.core.bus import bus
from app.domain.store import store
from app.api.mappers.player_mapper import player_to_out
from app.functions.export_import.session_paths import saved_path, saved_deletion_path, validate_session_tree
from app.functions.geographic_mapping.map_store import MapStore
from app.functions.geographic_mapping.session_integration import (
    begin_session_import, clear_views, get_lifecycle, get_map_store, get_timeline_store,
)



router = APIRouter()

# Have to add error handling and finish the import stuff

SAVED_SESSIONS_DIR = os.path.join(settings.backend_root_path, "data", "SavedSessions")
DATA_DIR = os.path.join(settings.backend_root_path, "data")


@router.post("/export")
async def export_session(req: ExportRequest) -> None:
    def export():
        folder = saved_path(SAVED_SESSIONS_DIR, req.campaign_name, req.session_name)
        validate_session_tree(folder)
        # Validate active views before touching an existing saved session.
        graph = get_map_store().get_map()
        timeline = get_timeline_store()
        events = timeline.snapshot()
        if not store.group.players:
            raise HTTPException(400, "Can not save session without active players")
        if not Path(settings.chroma_db_path).is_dir():
            raise HTTPException(404, "Source folder for DB does not exist")

        def prepare(staging):
            export_group_to_json(str(staging))
            export_settings_to_json(str(staging))
            copy_chroma_db(str(staging))
            type(timeline)(staging / "timeline_events.json").replace_snapshot(events)
            MapStore(staging / "geographic_map.json").replace_map(graph)

        def validate(staging):
            validate_session_tree(staging)
            for filename in ("group.json", "settings.json", "timeline_events.json", "geographic_map.json"):
                if not (staging / filename).is_file():
                    raise ValueError(f"Incomplete export: missing {filename}")
            if not (staging / "chroma_db").is_dir():
                raise ValueError("Incomplete export: missing ChromaDB")
            group = read_group_from_json(str(staging / "group.json"))
            if group.leader_id() is None:
                raise ValueError("Exported session has no leader")
            read_settings_from_json(str(staging / "settings.json"))
            if (type(timeline).load_snapshot(staging / "timeline_events.json") != events
                    or MapStore(staging / "geographic_map.json").get_map() != graph):
                raise ValueError("Exported views do not match the active snapshots")

        staged_export(folder, prepare, validate)

    await get_lifecycle().run(lambda: asyncio.to_thread(export))


@router.post("/import")
async def import_session(req: ImportRequest, request: Request) -> PlayerOut:
    async def restore():
        def validate():
            folder = saved_path(SAVED_SESSIONS_DIR, req.campaign_name, req.session_name)
            if not folder.is_dir():
                raise HTTPException(404, "Saved session does not exist")
            validate_session_tree(folder)
            if not (folder / "chroma_db").is_dir():
                raise HTTPException(404, "Saved session has no ChromaDB")
            try:
                graph = MapStore(folder / "geographic_map.json").get_map()
                events = type(get_timeline_store()).load_snapshot(folder / "timeline_events.json")
                group = read_group_from_json(str(folder / "group.json"))
                values = read_settings_from_json(str(folder / "settings.json"))
                if group.leader_id() is None:
                    raise ValueError("Saved session has no leader")
            except HTTPException:
                raise
            except Exception as error:
                raise HTTPException(409, "Saved session data is invalid; import cancelled") from error
            return folder, graph, events, group, values

        folder, graph, events, group, values = await asyncio.to_thread(validate)
        # Preflight errors above preserve the current valid views. Once the
        # legacy import starts, partial changes require empty derived views.
        await asyncio.to_thread(begin_session_import)

        def import_active():
            load_settings_from_json(str(folder / "settings.json"), values)
            leader = load_groups_from_json(str(folder / "group.json"), group)
            replace_chroma_db(str(folder), DATA_DIR)
            return leader

        try:
            leader = await asyncio.to_thread(import_active)
            result = player_to_out(leader, request)
            await asyncio.to_thread(get_timeline_store().replace_snapshot, events)
            await asyncio.to_thread(get_map_store().replace_map, graph)
            await bus.publish({
                "type": "session_imported",
                "players": [p.name for p in store.group.players.values()],
            })
            return result
        except Exception:
            await asyncio.to_thread(clear_views)
            raise

    return await get_lifecycle().run(restore)


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
async def delete_campaign_or_session(req: DeleteRequest):
    def delete():
        folder = saved_deletion_path(SAVED_SESSIONS_DIR, req.campaign_or_session_name)
        if not folder.is_dir():
            raise HTTPException(404, "Saved campaign/session does not exist")
        # No active saved-session ID exists. Conservatively clear both views
        # for any valid deletion attempt, including a partially failed rmtree.
        clear_views()
        delete_folder(req.campaign_or_session_name)

    await get_lifecycle().run(lambda: asyncio.to_thread(delete))


@router.post("/renameSession")
async def rename_session(req: RenameRequest):
    def rename():
        saved_path(SAVED_SESSIONS_DIR, req.campaign_name, req.old_session_name)
        saved_path(SAVED_SESSIONS_DIR, req.campaign_name, req.new_session_name)
        # Both JSON snapshots follow the folder; active data is a separate copy.
        rename_folder(req.campaign_name, req.old_session_name, req.new_session_name)

    await get_lifecycle().run(lambda: asyncio.to_thread(rename))
