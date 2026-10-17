"""Exercise map registration through the normal app without model startup."""

import importlib.util
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import Mock, patch

from fastapi import APIRouter
import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routers import health, map as map_routes, root
from app.base_models.map_models import MapData
from app.core.config import settings
from app.functions.geographic_mapping.map_store import MapStore


class MapAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Keep the real map, root and health routers. The other routers import
        # unrelated model stacks, so isolate them while executing real main.py.
        routers = types.ModuleType("app.api.routers")
        routers.__path__ = []
        for name in (
            "players", "llm", "config_router", "ws_players", "process_audio_data",
            "export_import_session", "rulebook_markdown", "entity_extraction", "timeline",
        ):
            module = types.ModuleType(f"app.api.routers.{name}")
            module.router = APIRouter()
            setattr(routers, name, module)
        routers.map, routers.root, routers.health = map_routes, root, health

        embedding = types.ModuleType("app.functions.embedding.embedding_model")
        self.startup_functions = []
        for name in (
            "embedd_rulebook", "read_text_files", "delete_chromadb",
            "delete_transcription_embeddings", "has_rulebook_embeddings",
        ):
            function = Mock(name=name)
            setattr(embedding, name, function)
            self.startup_functions.append(function)
        uvicorn = types.ModuleType("uvicorn")
        uvicorn.run = Mock()
        bus = types.ModuleType("app.core.bus")
        bus.bus = Mock()

        spec = importlib.util.spec_from_file_location(
            "_map_normal_app_test", BACKEND_DIR / "app/main.py",
        )
        main = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            "app.api.routers": routers,
            "app.functions.embedding.embedding_model": embedding,
            "uvicorn": uvicorn,
            "app.core.bus": bus,
        }), patch.dict(os.environ, {"DEBUG": "false"}), \
                patch("asyncio.set_event_loop_policy"), patch("logging.basicConfig"):
            spec.loader.exec_module(main)
            self.app = main.create_app()
        self.startup_app = main.app
        self.main = main

        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = MapStore(Path(temporary.name) / "map.json")
        self.app.dependency_overrides[map_routes.get_map_store] = lambda: self.store
        # ASGITransport does not run the app lifespan or initialize model stacks.
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_normal_startup_and_factory_register_map_contract(self):
        for app in (self.startup_app, self.app):
            self.assertEqual(app.title, settings.app_name)
            routes = {
                (route.path, method): route
                for route in app.routes
                for method in getattr(route, "methods", ())
            }
            for key in (("/map", "GET"), ("/map/generate", "POST")):
                self.assertIn(key, routes)
                self.assertIs(routes[key].response_model, MapData)

        self.assertEqual((await self.client.get("/")).json(), {
            "message": "Hello I am the root!",
        })
        health_response = await self.client.get("/health/checkConnection")
        self.assertEqual(health_response.status_code, 204)
        self.assertEqual(health_response.headers["cache-control"], "no-store")

    async def test_normal_app_returns_persists_and_reads_direct_map_data(self):
        generated = MapData.model_validate_json(
            (BACKEND_DIR / "tests/data/map_sample.json").read_text(encoding="utf-8")
        )
        with patch.object(map_routes, "generate_map", return_value=generated) as generate:
            empty = await self.client.get("/map")
            self.assertEqual(empty.status_code, 200)
            self.assertEqual(empty.json(), MapData().model_dump(mode="json"))
            generate.assert_not_called()
            self.assertFalse(self.store.file_path.exists())

            response = await self.client.post("/map/generate")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), generated.model_dump(mode="json"))
            self.assertEqual(self.store.get_map(), generated)
            saved = await self.client.get("/map")
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json(), response.json())
            generate.assert_called_once_with()
        for function in self.startup_functions:
            function.assert_not_called()

    async def test_lifespan_invalidates_imported_views_before_temporary_database_cleanup(self):
        calls = []
        self.main.has_rulebook_embeddings.return_value = True
        with patch.object(self.main, "invalidate_imported_views_on_startup",
                          side_effect=lambda: calls.append("views")), \
             patch.object(self.main, "delete_chromadb", side_effect=lambda *args: calls.append("cleanup")):
            async with self.main.lifespan(self.app):
                self.assertEqual(calls, ["views", "cleanup"])
        self.assertEqual(calls, ["views", "cleanup", "cleanup"])
        self.main.embedd_rulebook.assert_not_called()


if __name__ == "__main__":
    unittest.main()
