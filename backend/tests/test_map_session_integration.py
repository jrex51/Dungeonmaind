"""Offline lifecycle tests with real JSON, session helpers and HTTP routers.

WhisperX/embedding calls are mocked. Audio handlers are called directly because
the lightweight CI environment deliberately does not install multipart parsing.
"""

import asyncio
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from threading import Event
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, HTTPException, UploadFile
import httpx
from starlette.datastructures import Headers

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routers import map as map_routes
from app.base_models.config_base_models import ConfigRequest
from app.base_models.map_models import MapData
from app.base_models.timeline_models import TimelineEvent
from app.core.config import settings
from app.domain.models import Group, Role
from app.domain.store import store as group_store
from app.functions.geographic_mapping import session_integration as integration
from app.functions.geographic_mapping.map_store import MapStore


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SessionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Restore every setting and the in-memory group after each test.
        for name in type(settings).model_fields:
            self.enterContext(patch.object(settings, name, getattr(settings, name)))
        self.enterContext(patch.object(settings, "_chroma_db_path", None))
        settings.backend_root_path = str(self.root)
        settings.app_name = "Saved campaign"
        settings.debug = False
        self.group = Group()
        self.leader = self.group.add_player("DM", Role.leader)
        self.enterContext(patch.object(group_store, "group", self.group))

        timeline_module = load_module("_lifecycle_timeline_store", "app/functions/timeline/timeline_store.py")
        self.timeline = timeline_module.timeline_store
        self.map = MapStore(self.root / "data/geographic_map.json")
        self.graph = MapData.model_validate_json(
            (BACKEND_DIR / "tests/data/map_sample.json").read_text(encoding="utf-8")
        )
        self.events = [TimelineEvent(
            id="original-event-id", title="The cave", description="A cave east of the river.",
            category="discovery", start_time=5, end_time=10, locations=["cave", "river"],
            source_segments=[dict(text="A cave east of the river.", start_time=5, end_time=10)],
            created_at="2026-10-17T10:00:00Z", updated_at="2026-10-17T10:01:00Z",
        )]
        self.reset_views()
        self.life = integration.SessionLifecycle()
        for name, value in (("get_map_store", self.map), ("get_timeline_store", self.timeline),
                            ("get_lifecycle", self.life)):
            self.enterContext(patch.object(integration, name, return_value=value))

        # Execute the real lightweight session helpers against temporary roots.
        self.exports = load_module("_lifecycle_exports", "app/functions/export_import/export_session.py")
        self.imports = load_module("_lifecycle_imports", "app/functions/export_import/import_session.py")
        self.deletes = load_module("_lifecycle_deletes", "app/functions/export_import/delete_session.py")
        with patch.dict(sys.modules, {
            "app.functions.export_import.export_session": self.exports,
            "app.functions.export_import.import_session": self.imports,
            "app.functions.export_import.delete_session": self.deletes,
        }):
            self.sessions = load_module("_lifecycle_session_routes", "app/api/routers/export_import_session.py")

        generator = types.ModuleType("app.functions.timeline.timeline_generator")
        self.generate_timeline = Mock(return_value=(self.events, 1))
        generator.generate_timeline_from_embeddings = self.generate_timeline
        with patch.dict(sys.modules, {
            "app.functions.timeline.timeline_generator": generator,
            "app.functions.timeline.timeline_store": timeline_module,
        }):
            self.timeline_routes = load_module("_lifecycle_timeline_routes", "app/api/routers/timeline.py")

        embeddings = types.ModuleType("app.functions.embedding.embedding_model")
        self.delete_transcripts = Mock()
        embeddings.delete_transcription_embeddings = self.delete_transcripts
        embeddings.reembed_chroma_entries = Mock()
        transcription = types.ModuleType("app.functions.process_audio_data.transcribe_audio")
        self.transcribe = AsyncMock(return_value=[dict(start=0, end=1, text="New evidence")])
        transcription.transcribe_audio = self.transcribe
        self.decoded_audio = Mock(name="decoded_audio")
        self.decode = Mock(return_value=self.decoded_audio)
        transcription.decode_audio_bytes = self.decode
        transcription.reload_transcription_model = Mock()
        with patch.dict(sys.modules, {
            "app.functions.embedding.embedding_model": embeddings,
            "app.functions.process_audio_data.transcribe_audio": transcription,
        }):
            # No multipart dependency: execute the real audio handler directly.
            registration = Mock()
            registration.post.return_value = lambda function: function
            with patch("fastapi.APIRouter", return_value=registration):
                self.audio = load_module("_lifecycle_audio_routes", "app/api/routers/process_audio_data.py")
            self.config = load_module("_lifecycle_config_routes", "app/api/routers/config_router.py")

        map_store_dependency = map_routes.get_map_store
        for module in (self.sessions, self.timeline_routes, self.audio, self.config, map_routes):
            self.enterContext(patch.object(module, "get_lifecycle", return_value=self.life))
            if hasattr(module, "get_map_store"):
                self.enterContext(patch.object(module, "get_map_store", return_value=self.map))
            if hasattr(module, "get_timeline_store"):
                self.enterContext(patch.object(module, "get_timeline_store", return_value=self.timeline))
        self.publish = self.enterContext(patch.object(self.sessions.bus, "publish", new=AsyncMock()))
        app = FastAPI()
        app.include_router(self.sessions.router, prefix="/exportImport")
        app.include_router(self.timeline_routes.router, prefix="/timeline")
        app.include_router(map_routes.router, prefix="/map")
        app.include_router(self.config.router, prefix="/config")
        app.dependency_overrides[map_store_dependency] = lambda: self.map
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        )
        self.addAsyncCleanup(self.client.aclose)
        self.saved = self.root / "data/SavedSessions"
        self.body = dict(campaign_name="campaign", session_name="session")
        self.folder = self.saved / "campaign/session"
        self.db = self.root / "data/chroma_db"
        self.db.mkdir(parents=True)
        (self.db / "evidence.txt").write_text("Saved transcript", encoding="utf-8")

    def reset_views(self):
        self.map.replace_map(self.graph)
        self.timeline.replace_snapshot(self.events)

    def assert_empty_views(self):
        self.assertEqual(self.map.get_map(), MapData())
        self.assertEqual(self.timeline.list_events(), [])

    def assert_original_views(self):
        self.assertEqual(self.map.get_map(), self.graph)
        self.assertEqual(self.timeline.list_events(), self.events)

    async def export(self):
        response = await self.client.post("/exportImport/export", json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json())  # Preserve the existing response schema.

    def session_contents(self, folder=None):
        folder = self.folder if folder is None else folder
        return {path.relative_to(folder).as_posix(): path.read_bytes() if path.is_file() else None
                for path in folder.rglob("*")}

    def assert_no_export_workdirs(self):
        self.assertEqual(list(self.folder.parent.glob(".session-export-*")), [])
        self.assertEqual(list(self.folder.parent.glob(".session-backup-*")), [])

    def upload(self, content=b"fake audio", content_type="audio/wav"):
        return UploadFile(BytesIO(content), filename="session.wav",
                          headers=Headers({"content-type": content_type}))

    async def test_export_import_roundtrip_preserves_views_group_settings_and_database(self):
        await self.export()
        self.assertEqual(MapStore(self.folder / "geographic_map.json").get_map(), self.graph)
        self.assertEqual(type(self.timeline).load_snapshot(self.folder / "timeline_events.json"), self.events)
        self.assertEqual((self.folder / "chroma_db/evidence.txt").read_text(), "Saved transcript")
        self.map.clear_map()
        self.timeline.clear_events()
        settings.app_name = "Different active session"
        data = json.loads((self.folder / "settings.json").read_text())
        data["backend_root_path"] = str(self.root / "foreign-machine")
        (self.folder / "settings.json").write_text(json.dumps(data))
        response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], str(self.leader.id))
        self.assertEqual(response.json()["backend_url"], "http://test")
        self.assert_original_views()
        self.assertEqual(settings.app_name, "Saved campaign")
        self.assertEqual(settings.backend_root_path, str(self.root))
        self.assertEqual((Path(settings.chroma_db_path) / "evidence.txt").read_text(), "Saved transcript")
        self.publish.assert_awaited_once_with({"type": "session_imported", "players": ["DM"]})

    async def test_repeated_imports_use_distinct_database_copies(self):
        await self.export()
        paths = []
        for _ in range(2):
            response = await self.client.post("/exportImport/import", json=self.body)
            self.assertEqual(response.status_code, 200, response.text)
            paths.append(settings.chroma_db_path)
        self.assertNotEqual(*paths)
        self.assert_original_views()

    async def test_startup_invalidates_imported_views_without_touching_saved_snapshots(self):
        # Ordinary persistent views survive startup.
        integration.invalidate_imported_views_on_startup()
        self.assert_original_views()
        await self.export()
        response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        marker = Path(self.timeline.file_path).with_name("imported_session_views.flag")
        self.assertTrue(marker.exists())
        integration.invalidate_imported_views_on_startup()
        self.assert_empty_views()
        self.assertFalse(marker.exists())
        self.assertEqual(MapStore(self.folder / "geographic_map.json").get_map(), self.graph)
        self.assertEqual(type(self.timeline).load_snapshot(self.folder / "timeline_events.json"), self.events)
        # Idempotent startup cleanup must not erase a newly generated map.
        self.reset_views()
        integration.invalidate_imported_views_on_startup()
        self.assert_original_views()

    async def test_legacy_import_without_snapshots_clears_previous_views(self):
        await self.export()
        (self.folder / "geographic_map.json").unlink()
        (self.folder / "timeline_events.json").unlink()
        response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_empty_views()

    async def test_partial_legacy_import_restores_only_the_available_snapshot(self):
        await self.export()
        (self.folder / "geographic_map.json").unlink()
        response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.map.get_map(), MapData())
        self.assertEqual(self.timeline.list_events(), self.events)

    async def test_invalid_saved_files_cancel_before_active_mutation(self):
        await self.export()
        for filename, invalid in (
            ("geographic_map.json", "broken"),
            ("geographic_map.json", '{"source_segment_count": -1}'),
            ("timeline_events.json", '{}'),
            ("timeline_events.json", '[{"title": "missing fields"}]'),
            ("settings.json", '{"debug": "not a boolean"}'),
            ("group.json", '{"players": []}'),
        ):
            with self.subTest(filename=filename, invalid=invalid):
                path = self.folder / filename
                previous = path.read_bytes()
                path.write_text(invalid)
                active_group = group_store.group
                with patch.object(self.sessions, "load_settings_from_json") as change_settings, \
                     patch.object(self.sessions, "replace_chroma_db") as change_database:
                    response = await self.client.post("/exportImport/import", json=self.body)
                self.assertIn(response.status_code, (400, 409), response.text)
                change_settings.assert_not_called()
                change_database.assert_not_called()
                self.assertIs(group_store.group, active_group)
                self.assert_original_views()
                self.assertEqual(path.read_text(), invalid)
                path.write_bytes(previous)
        self.publish.assert_not_awaited()

    async def test_missing_session_or_database_preserves_active_views(self):
        response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 404)
        await self.export()
        shutil.rmtree(self.folder / "chroma_db")
        response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 404)
        self.assert_original_views()

    async def test_partial_import_failure_leaves_both_views_empty(self):
        await self.export()
        settings.app_name = "Previous session"
        with patch.object(self.sessions, "replace_chroma_db", side_effect=OSError("copy failure")):
            response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(settings.app_name, "Saved campaign")  # Legacy helpers may partially mutate.
        self.assert_empty_views()
        self.publish.assert_not_awaited()
        self.assertEqual(MapStore(self.folder / "geographic_map.json").get_map(), self.graph)

    async def test_import_restore_or_notification_failure_clears_derived_views(self):
        await self.export()
        original_replace = self.map.replace_map

        def fail_nonempty(graph):
            if graph.nodes:
                raise OSError("write failure")
            return original_replace(graph)

        with patch.object(self.map, "replace_map", side_effect=fail_nonempty):
            response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 500)
        self.assert_empty_views()
        self.publish.side_effect = RuntimeError("notification failure")
        response = await self.client.post("/exportImport/import", json=self.body)
        self.assertEqual(response.status_code, 500)
        self.assert_empty_views()

    async def test_export_rejects_invalid_active_views_before_overwriting_saved_data(self):
        await self.export()
        for store_path in (self.map.file_path, Path(self.timeline.file_path)):
            with self.subTest(path=store_path.name):
                before = {p.name: p.read_bytes() for p in self.folder.glob("*.json")}
                old = store_path.read_bytes()
                store_path.write_text("invalid json")
                response = await self.client.post("/exportImport/export", json=self.body)
                self.assertEqual(response.status_code, 500)
                self.assertEqual({p.name: p.read_bytes() for p in self.folder.glob("*.json")}, before)
                store_path.write_bytes(old)

    async def test_failed_reexport_preserves_entire_original_session(self):
        await self.export()
        before = self.session_contents()
        settings.app_name = "Replacement session"
        (self.db / "evidence.txt").write_text("New evidence")
        for step in ("export_group_to_json", "export_settings_to_json", "copy_chroma_db"):
            with self.subTest(step=step):
                with patch.object(self.sessions, step, side_effect=OSError("preparation failure")):
                    response = await self.client.post("/exportImport/export", json=self.body)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(self.session_contents(), before)
                self.assert_no_export_workdirs()
        self.assert_original_views()

    async def test_partial_database_copy_only_writes_to_staging(self):
        await self.export()
        before = self.session_contents()

        def fail_copy(folder):
            staging = Path(folder)
            self.assertEqual(staging.parent, self.folder.parent)
            self.assertNotEqual(staging, self.folder)
            (staging / "chroma_db").mkdir()
            (staging / "chroma_db/partial.txt").write_text("Incomplete copy")
            raise OSError("copy interrupted")

        with patch.object(self.sessions, "copy_chroma_db", side_effect=fail_copy):
            response = await self.client.post("/exportImport/export", json=self.body)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.session_contents(), before)
        self.assert_no_export_workdirs()

    async def test_staged_export_must_validate_before_moving_original(self):
        await self.export()
        before = self.session_contents()

        def invalid_settings(folder):
            (Path(folder) / "settings.json").write_text('{"debug": "invalid boolean"}')

        for step, replacement in (("export_settings_to_json", invalid_settings),
                                  ("copy_chroma_db", lambda folder: None)):
            with self.subTest(step=step):
                with patch.object(self.sessions, step, side_effect=replacement), \
                     patch.object(self.exports.os, "rename") as rename:
                    response = await self.client.post("/exportImport/export", json=self.body)
                self.assertEqual(response.status_code, 500)
                rename.assert_not_called()
                self.assertEqual(self.session_contents(), before)
                self.assert_no_export_workdirs()

    async def test_reexport_replaces_complete_session_and_removes_workdirs(self):
        await self.export()
        (self.folder / "obsolete.txt").write_text("Old session only")
        settings.app_name = "Replacement session"
        (self.db / "evidence.txt").write_text("Replacement transcript")
        self.map.clear_map()
        self.timeline.clear_events()
        await self.export()
        self.assertFalse((self.folder / "obsolete.txt").exists())
        self.assertEqual(json.loads((self.folder / "settings.json").read_text())["app_name"], "Replacement session")
        self.assertEqual((self.folder / "chroma_db/evidence.txt").read_text(), "Replacement transcript")
        self.assertEqual(MapStore(self.folder / "geographic_map.json").get_map(), MapData())
        self.assertEqual(type(self.timeline).load_snapshot(self.folder / "timeline_events.json"), [])
        self.assert_no_export_workdirs()

    async def test_failed_directory_replacement_restores_original_on_windows(self):
        await self.export()
        before = self.session_contents()
        original_rename = self.exports.os.rename

        for blocked_step in ("backup", "promotion"):
            with self.subTest(blocked_step=blocked_step):
                def fail_rename(source, destination):
                    source = Path(source)
                    if ((blocked_step == "backup" and source == self.folder)
                            or (blocked_step == "promotion" and source.name.startswith(".session-export-"))):
                        raise PermissionError("Windows directory is locked")
                    return original_rename(source, destination)

                with patch.object(self.exports.os, "rename", side_effect=fail_rename) as rename:
                    response = await self.client.post("/exportImport/export", json=self.body)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(rename.call_count, 1 if blocked_step == "backup" else 3)
                self.assertEqual(self.session_contents(), before)
                self.assert_no_export_workdirs()
                self.assert_original_views()

    async def test_failed_first_export_does_not_publish_partial_session(self):
        for step in ("preparation", "promotion"):
            with self.subTest(step=step):
                target = self.sessions if step == "preparation" else self.exports.os
                attribute = "copy_chroma_db" if step == "preparation" else "rename"
                with patch.object(target, attribute, side_effect=OSError("export failed")):
                    response = await self.client.post("/exportImport/export", json=self.body)
                self.assertEqual(response.status_code, 500)
                self.assertFalse(self.folder.exists())
                self.assert_no_export_workdirs()
                self.assert_original_views()

    async def test_blocked_rollback_retains_original_backup_and_reports_recovery_path(self):
        await self.export()
        before = self.session_contents()
        original_rename = self.exports.os.rename

        def block_promotion_and_rollback(source, destination):
            if Path(source) != self.folder:
                raise PermissionError("Windows blocks promotion and rollback")
            return original_rename(source, destination)

        with patch.object(self.exports.os, "rename", side_effect=block_promotion_and_rollback), \
             self.assertLogs(self.exports.logger, level="ERROR"):
            response = await self.client.post("/exportImport/export", json=self.body)
        self.assertEqual(response.status_code, 500)
        backups = list(self.folder.parent.glob(".session-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.session_contents(backups[0]), before)
        self.assertIn(str(backups[0]), response.json()["detail"])
        self.assertEqual(list(self.folder.parent.glob(".session-export-*")), [])
        self.assert_original_views()

    async def test_backup_cleanup_failure_keeps_successful_export_and_original_backup(self):
        await self.export()
        before = self.session_contents()
        settings.app_name = "Replacement session"
        original_remove = self.exports._remove_export_directory

        def fail_backup_cleanup(path, parent):
            if path.name.startswith(".session-backup-"):
                raise PermissionError("Backup still open")
            return original_remove(path, parent)

        with patch.object(self.exports, "_remove_export_directory", side_effect=fail_backup_cleanup), \
             self.assertLogs(self.exports.logger, level="WARNING"):
            await self.export()
        self.assertEqual(json.loads((self.folder / "settings.json").read_text())["app_name"], "Replacement session")
        backups = list(self.folder.parent.glob(".session-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.session_contents(backups[0]), before)

    async def test_database_copy_helper_never_deletes_existing_destination(self):
        await self.export()
        before = self.session_contents()
        with self.assertRaises(FileExistsError):
            self.exports.copy_chroma_db(str(self.folder))
        self.assertEqual(self.session_contents(), before)

    async def test_export_without_source_database_preserves_existing_saved_views(self):
        await self.export()
        settings.chroma_db_path = str(self.root / "missing-database")
        response = await self.client.post("/exportImport/export", json=self.body)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(MapStore(self.folder / "geographic_map.json").get_map(), self.graph)
        self.assertEqual(type(self.timeline).load_snapshot(self.folder / "timeline_events.json"), self.events)
        self.assert_original_views()

    async def test_rename_moves_both_snapshots_and_preserves_active_views(self):
        await self.export()
        response = await self.client.post("/exportImport/renameSession", json={
            "campaign_name": "campaign", "old_session_name": "session", "new_session_name": "renamed",
        })
        self.assertEqual(response.status_code, 200, response.text)
        renamed = self.saved / "campaign/renamed"
        self.assertFalse(self.folder.exists())
        self.assertEqual(MapStore(renamed / "geographic_map.json").get_map(), self.graph)
        self.assertEqual(type(self.timeline).load_snapshot(renamed / "timeline_events.json"), self.events)
        self.assert_original_views()

    async def test_rename_never_overwrites_an_existing_session(self):
        await self.export()
        (self.saved / "campaign/existing").mkdir()
        response = await self.client.post("/exportImport/renameSession", json={
            "campaign_name": "campaign", "old_session_name": "session", "new_session_name": "existing",
        })
        self.assertEqual(response.status_code, 409)
        self.assertTrue(self.folder.is_dir())
        self.assert_original_views()

    async def test_delete_session_or_campaign_invalidates_both_active_views(self):
        for target in ("campaign/session", "campaign"):
            with self.subTest(target=target):
                self.reset_views()
                await self.export()
                response = await self.client.post("/exportImport/deleteCampaignsOrSessions",
                                                  json={"campaign_or_session_name": target})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse((self.saved / target).exists())
                self.assert_empty_views()

    async def test_missing_delete_preserves_views_but_partial_delete_failure_invalidates(self):
        response = await self.client.post("/exportImport/deleteCampaignsOrSessions",
                                          json={"campaign_or_session_name": "missing"})
        self.assertEqual(response.status_code, 404)
        self.assert_original_views()
        await self.export()
        with patch.object(self.sessions, "delete_folder", side_effect=OSError("partial delete")):
            response = await self.client.post("/exportImport/deleteCampaignsOrSessions",
                                              json={"campaign_or_session_name": "campaign/session"})
        self.assertEqual(response.status_code, 500)
        self.assert_empty_views()

    async def test_all_session_mutations_reject_path_traversal_before_side_effects(self):
        await self.export()
        for invalid in ("../outside", "/absolute", "C:/outside", "C:relative", "..\\outside",
                        "\\\\server\\share", ".", "", "campaign/../outside", "session:stream"):
            cases = [
                ("export", {**self.body, "campaign_name": invalid}),
                ("import", {**self.body, "session_name": invalid}),
                ("deleteCampaignsOrSessions", {"campaign_or_session_name": invalid}),
                ("renameSession", dict(campaign_name="campaign", old_session_name="session",
                                       new_session_name=invalid)),
            ]
            for endpoint, body in cases:
                with self.subTest(endpoint=endpoint, path=invalid):
                    response = await self.client.post("/exportImport/" + endpoint, json=body)
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assert_original_views()
                    self.assertTrue(self.folder.is_dir())

    async def test_original_request_validation_is_preserved(self):
        for endpoint in ("export", "import", "renameSession", "deleteCampaignsOrSessions"):
            response = await self.client.post("/exportImport/" + endpoint, json={})
            self.assertEqual(response.status_code, 422)
        self.assert_original_views()

    async def test_nested_campaign_and_session_names_are_rejected(self):
        await self.export()
        before = self.session_contents()
        for endpoint in ("export", "import", "renameSession"):
            body = (self.body if endpoint != "renameSession" else
                    dict(campaign_name="campaign", old_session_name="session", new_session_name="renamed"))
            for field in body:
                with self.subTest(endpoint=endpoint, field=field):
                    response = await self.client.post("/exportImport/" + endpoint,
                                                      json={**body, field: body[field] + "/nested"})
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertEqual(self.session_contents(), before)
                    self.assert_original_views()
        with self.assertRaises(HTTPException):
            self.exports.get_folder_name("campaign/nested", "session")
        with self.assertRaises(HTTPException):
            self.exports.rename_folder("campaign", "session/chroma_db", "renamed")
        self.assertEqual(self.session_contents(), before)

    async def test_delete_rejects_internal_session_directories_without_invalidating_views(self):
        await self.export()
        (self.folder / "chroma_db/internal").mkdir()
        before = self.session_contents()
        for target in ("campaign/session/chroma_db", "campaign/session/chroma_db/internal"):
            with self.subTest(target=target):
                response = await self.client.post("/exportImport/deleteCampaignsOrSessions",
                                                  json={"campaign_or_session_name": target})
                self.assertEqual(response.status_code, 400, response.text)
                with self.assertRaises(HTTPException) as error:
                    self.deletes.delete_folder(target)
                self.assertEqual(error.exception.status_code, 400)
                self.assertEqual(self.session_contents(), before)
                self.assert_original_views()

    async def test_session_and_file_links_cannot_redirect_import_export_or_delete(self):
        await self.export()
        outside = self.root / "outside-saved-sessions"
        outside.mkdir()
        marker = outside / "marker.json"
        marker.write_text("Must remain untouched")
        link = self.saved / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Creating symbolic links is unavailable: {error}")
        for endpoint, body in (
            ("export", dict(campaign_name="linked", session_name="session")),
            ("import", dict(campaign_name="linked", session_name="session")),
            ("deleteCampaignsOrSessions", dict(campaign_or_session_name="linked")),
            ("renameSession", dict(campaign_name="linked", old_session_name="old", new_session_name="new")),
        ):
            response = await self.client.post("/exportImport/" + endpoint, json=body)
            self.assertEqual(response.status_code, 400, response.text)
        (self.folder / "geographic_map.json").unlink()
        (self.folder / "geographic_map.json").symlink_to(marker)
        for endpoint in ("export", "import"):
            response = await self.client.post("/exportImport/" + endpoint, json=self.body)
            self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(marker.read_text(), "Must remain untouched")
        self.assert_original_views()

    async def test_directory_junction_paths_are_rejected_before_side_effects(self):
        await self.export()
        with patch.object(Path, "is_junction", autospec=True,
                          side_effect=lambda path: path.name == "campaign"):
            for endpoint, body in (
                ("export", self.body), ("import", self.body),
                ("deleteCampaignsOrSessions", {"campaign_or_session_name": "campaign/session"}),
                ("renameSession", dict(campaign_name="campaign", old_session_name="session", new_session_name="new")),
            ):
                response = await self.client.post("/exportImport/" + endpoint, json=body)
                self.assertEqual(response.status_code, 400, response.text)
        self.assert_original_views()
        self.assertTrue(self.folder.is_dir())

    async def test_transcription_replace_and_append_invalidate_without_generating(self):
        for replace in (True, False):
            with self.subTest(replace=replace):
                self.reset_views()
                self.delete_transcripts.reset_mock()
                result = await self.audio.transcribe_audio_file(self.upload(), replace_existing=replace, time_offset=5)
                self.assertEqual(result.output[0].text, "New evidence")
                self.assert_empty_views()
                self.assertEqual(self.delete_transcripts.call_count, int(replace))
                self.transcribe.assert_awaited_with(
                    b"fake audio", content_type="audio/wav", time_offset=5,
                    decoded_audio=self.decoded_audio,
                )
        self.generate_timeline.assert_not_called()

    async def test_invalid_audio_or_offset_does_not_destroy_existing_views(self):
        for content, content_type, offset, status in (
            (b"audio", "text/plain", 0, 415), (b"", "audio/wav", 0, 400),
            (b"audio", "audio/wav", -1, 400), (b"audio", "audio/wav", float("nan"), 400),
        ):
            with self.subTest(status=status, offset=offset):
                with self.assertRaises(HTTPException) as error:
                    await self.audio.transcribe_audio_file(self.upload(content, content_type), time_offset=offset)
                self.assertEqual(error.exception.status_code, status)
                self.assert_original_views()
        self.delete_transcripts.assert_not_called()
        self.transcribe.assert_not_awaited()

    async def test_failed_transcription_or_deletion_keeps_both_views_invalidated(self):
        for replace in (True, False):
            self.reset_views()
            self.transcribe.side_effect = RuntimeError("partial transcription")
            with self.assertRaises(HTTPException) as error:
                await self.audio.transcribe_audio_file(self.upload(), replace_existing=replace)
            self.assertEqual(error.exception.status_code, 500)
            self.assert_empty_views()
        self.reset_views()
        self.delete_transcripts.side_effect = RuntimeError("partial deletion")
        with self.assertRaises(HTTPException):
            await self.audio.transcribe_audio_file(self.upload(), replace_existing=True)
        self.assert_empty_views()

    async def test_undecodable_audio_preserves_transcript_and_views(self):
        self.decode.side_effect = RuntimeError("FFmpeg cannot decode this upload")
        with self.assertRaises(HTTPException) as error:
            await self.audio.transcribe_audio_file(self.upload(), replace_existing=True)
        self.assertEqual(error.exception.status_code, 400)
        self.assert_original_views()
        self.delete_transcripts.assert_not_called()
        self.transcribe.assert_not_awaited()

    async def test_timeline_success_invalidates_map_and_failure_preserves_both_views(self):
        self.generate_timeline.side_effect = RuntimeError("model unavailable")
        response = await self.client.post("/timeline/generate")
        self.assertEqual(response.status_code, 500)
        self.assert_original_views()
        self.generate_timeline.side_effect = None
        self.generate_timeline.return_value = (self.events, -1)
        response = await self.client.post("/timeline/generate")
        self.assertEqual(response.status_code, 500)
        self.assert_original_views()
        self.generate_timeline.return_value = (self.events, 1)
        response = await self.client.post("/timeline/generate")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.map.get_map(), MapData())
        self.assertEqual(self.timeline.list_events()[0].locations, self.events[0].locations)

    async def test_config_transcript_deletion_invalidates_views(self):
        request = ConfigRequest(
            player_id=self.leader.id, selected_LLM=settings.llm_model,
            transcription_model=settings.transcription_model, embedding_model=settings.embedding_model,
            embedding_top_k=settings.embedding_top_k, delete_transcriptions=True,
        )
        response = await self.client.post("/config/changeConfig", json=request.model_dump(mode="json"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_empty_views()
        self.delete_transcripts.assert_called_once_with()

    async def test_failed_timeline_save_restores_valid_map_if_timeline_is_unchanged(self):
        with patch.object(self.timeline, "replace_events", side_effect=OSError("disk failure")):
            response = await self.client.post("/timeline/generate")
        self.assertEqual(response.status_code, 500)
        self.assert_original_views()

    async def test_failed_config_database_rebuild_keeps_views_invalidated(self):
        request = ConfigRequest(
            player_id=self.leader.id, selected_LLM=settings.llm_model,
            transcription_model=settings.transcription_model, embedding_model="all-MiniLM-L12-v2",
            embedding_top_k=settings.embedding_top_k,
        )
        with patch.object(self.config, "reembed_chroma_entries", side_effect=RuntimeError("partial rebuild")):
            response = await self.client.post("/config/changeConfig", json=request.model_dump(mode="json"))
        self.assertEqual(response.status_code, 500)
        self.assert_empty_views()

    async def test_timeline_save_that_changes_data_then_fails_keeps_map_empty(self):
        original_replace = self.timeline.replace_events

        def fail_after_commit(events):
            original_replace(events)
            raise OSError("failure after commit")

        with patch.object(self.timeline, "replace_events", side_effect=fail_after_commit):
            response = await self.client.post("/timeline/generate")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.map.get_map(), MapData())
        self.assertNotEqual(self.timeline.list_events()[0].id, self.events[0].id)

    async def test_timeline_snapshot_write_failure_preserves_previous_file(self):
        before = Path(self.timeline.file_path).read_bytes()
        with patch("os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.timeline.replace_snapshot([])
        self.assertEqual(Path(self.timeline.file_path).read_bytes(), before)
        self.assertEqual(list(Path(self.timeline.file_path).parent.glob("timeline-*.tmp")), [])

    async def test_mutations_wait_for_map_generation_while_get_remains_responsive(self):
        await self.export()
        for mutation in ("import", "timeline", "transcribe", "delete", "export", "rename"):
            with self.subTest(mutation=mutation):
                started, release = Event(), Event()

                def generate():
                    started.set()
                    if not release.wait(5):
                        raise RuntimeError("Generation worker timed out")
                    return self.graph

                with patch.object(map_routes, "generate_map", side_effect=generate):
                    generation = asyncio.create_task(self.client.post("/map/generate"))
                    pending = None
                    try:
                        self.assertTrue(await asyncio.to_thread(started.wait, 2))
                        if mutation == "import":
                            action = self.client.post("/exportImport/import", json=self.body)
                        elif mutation == "timeline":
                            action = self.client.post("/timeline/generate")
                        elif mutation == "transcribe":
                            action = self.audio.transcribe_audio_file(self.upload(), replace_existing=False)
                        elif mutation == "delete":
                            action = self.client.post("/exportImport/deleteCampaignsOrSessions",
                                                      json={"campaign_or_session_name": "campaign/session"})
                        elif mutation == "export":
                            action = self.client.post("/exportImport/export", json=self.body)
                        else:
                            action = self.client.post("/exportImport/renameSession", json={
                                "campaign_name": "campaign", "old_session_name": "session",
                                "new_session_name": "renamed",
                            })
                        pending = asyncio.create_task(action)
                        await asyncio.sleep(0.02)
                        self.assertFalse(pending.done())
                        read = await asyncio.wait_for(self.client.get("/map"), timeout=2)
                        self.assertEqual(read.status_code, 200)
                        self.assertFalse(generation.done())
                    finally:
                        release.set()
                        self.assertEqual((await generation).status_code, 200)
                        if pending:
                            result = await pending
                            if hasattr(result, "status_code"):
                                self.assertEqual(result.status_code, 200, result.text)
                if mutation in ("timeline", "transcribe", "delete"):
                    self.assertEqual(self.map.get_map(), MapData())
                self.reset_views()
                if not self.folder.exists():
                    await self.export()

    async def test_generation_waits_for_import_to_finish(self):
        await self.export()
        started, release = Event(), Event()
        original_import = self.sessions.replace_chroma_db

        def slow_import(*args):
            started.set()
            if not release.wait(5):
                raise RuntimeError("Import worker timed out")
            return original_import(*args)

        with patch.object(self.sessions, "replace_chroma_db", side_effect=slow_import), \
             patch.object(map_routes, "generate_map", return_value=self.graph) as generate:
            importing = asyncio.create_task(self.client.post("/exportImport/import", json=self.body))
            generating = None
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                generating = asyncio.create_task(self.client.post("/map/generate"))
                await asyncio.sleep(0.02)
                generate.assert_not_called()
                read = await asyncio.wait_for(self.client.get("/map"), timeout=2)
                self.assertEqual(read.json(), MapData().model_dump(mode="json"))
            finally:
                release.set()
                self.assertEqual((await importing).status_code, 200)
                if generating:
                    self.assertEqual((await generating).status_code, 200)
        self.assert_original_views()

    async def test_cancelled_generation_retains_lock_until_worker_finishes(self):
        started, release = Event(), Event()

        def generate():
            started.set()
            if not release.wait(5):
                raise RuntimeError("Generation worker timed out")
            return self.graph

        with patch.object(map_routes, "generate_map", side_effect=generate):
            generation = asyncio.create_task(self.client.post("/map/generate"))
            mutation = None
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                generation.cancel()
                mutation = asyncio.create_task(self.audio.transcribe_audio_file(self.upload()))
                await asyncio.sleep(0.02)
                self.transcribe.assert_not_awaited()
                self.assertFalse(mutation.done())
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await generation
                if mutation:
                    await mutation
        self.assert_empty_views()


if __name__ == "__main__":
    unittest.main()
