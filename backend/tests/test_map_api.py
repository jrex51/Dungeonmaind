"""Map API regressions using real storage and no model/database services."""

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, get_ident
import unittest
from unittest.mock import patch

from fastapi import FastAPI
import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routers import map as routes
from app.base_models.map_models import MapData
from app.base_models.timeline_models import TimelineEvent, TimelineSourceSegment
from app.functions.geographic_mapping import map_generator
from app.functions.geographic_mapping.map_store import MapStore


class MapAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = MapStore(Path(temporary.name) / "map.json")
        app = FastAPI()
        app.include_router(routes.router, prefix="/map")
        app.dependency_overrides[routes.get_map_store] = lambda: self.store
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        self.addAsyncCleanup(self.client.aclose)
        self.graph = MapData.model_validate_json(
            (BACKEND_DIR / "tests/data/map_sample.json").read_text(encoding="utf-8")
        )

    async def test_get_empty_does_not_write_or_generate(self):
        with patch.object(routes, "generate_map") as generate:
            for _ in range(3):
                response = await self.client.get("/map")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), MapData().model_dump(mode="json"))
        self.assertFalse(self.store.file_path.exists())
        generate.assert_not_called()

    async def test_generate_persists_full_map_and_get_does_not_regenerate(self):
        with patch.object(routes, "generate_map", return_value=self.graph) as generate:
            response = await self.client.post("/map/generate")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), self.graph.model_dump(mode="json"))
            before = self.store.file_path.read_bytes()
            for _ in range(3):
                read = await self.client.get("/map")
                self.assertEqual(read.status_code, 200)
                self.assertEqual(read.json(), response.json())
        self.assertEqual(self.store.file_path.read_bytes(), before)
        self.assertEqual(MapStore(self.store.file_path).get_map(), self.graph)
        generate.assert_called_once_with()

    async def test_successful_empty_generation_replaces_previous_map(self):
        self.store.replace_map(self.graph)
        with patch.object(routes, "generate_map", return_value=MapData()):
            response = await self.client.post("/map/generate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), MapData().model_dump(mode="json"))
        self.assertEqual(self.store.get_map(), MapData())

    async def test_generation_failure_preserves_previous_map(self):
        self.store.replace_map(self.graph)
        before = self.store.file_path.read_bytes()
        with patch.object(routes, "generate_map", side_effect=RuntimeError("offline")), \
             self.assertLogs(routes.logger, level="ERROR"):
            response = await self.client.post("/map/generate")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {
            "detail": "Map generation failed; previous map retained"
        })
        self.assertEqual(self.store.file_path.read_bytes(), before)
        read = await self.client.get("/map")
        self.assertEqual(read.json(), self.graph.model_dump(mode="json"))

    async def test_invalid_generated_graph_preserves_previous_map(self):
        self.store.replace_map(self.graph)
        before = self.store.file_path.read_bytes()
        self.graph.edges[0].target = "unknown-node"
        with patch.object(routes, "generate_map", return_value=self.graph), \
             self.assertLogs(routes.logger, level="ERROR"):
            response = await self.client.post("/map/generate")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.store.file_path.read_bytes(), before)

    async def test_storage_failure_returns_error_and_preserves_previous_map(self):
        self.store.replace_map(self.graph)
        before = self.store.file_path.read_bytes()
        with patch.object(routes, "generate_map", return_value=MapData()), \
             patch("app.functions.geographic_mapping.map_store.os.replace",
                   side_effect=OSError("disk failure")), \
             self.assertLogs(routes.logger, level="ERROR"):
            response = await self.client.post("/map/generate")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.store.file_path.read_bytes(), before)
        self.assertEqual(list(self.store.file_path.parent.glob("*.tmp")), [])

    async def test_corrupt_storage_returns_error_without_overwriting(self):
        for content in ("invalid json", '{"source_segment_count": -1}'):
            with self.subTest(content=content):
                self.store.file_path.write_text(content, encoding="utf-8")
                with self.assertLogs(routes.logger, level="ERROR"):
                    response = await self.client.get("/map")
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.json(), {"detail": "Unable to read the stored map"})
                self.assertEqual(self.store.file_path.read_text(encoding="utf-8"), content)

    async def test_generation_and_file_operations_run_off_event_loop(self):
        loop_thread = get_ident()
        worker_threads = {}
        original_read = self.store.get_map
        original_replace = self.store.replace_map

        def generate():
            worker_threads["generate"] = get_ident()
            return self.graph

        def read():
            worker_threads["read"] = get_ident()
            return original_read()

        def replace(graph):
            worker_threads["write"] = get_ident()
            return original_replace(graph)

        with patch.object(routes, "generate_map", side_effect=generate), \
             patch.object(self.store, "get_map", side_effect=read), \
             patch.object(self.store, "replace_map", side_effect=replace):
            self.assertEqual((await self.client.post("/map/generate")).status_code, 200)
            self.assertEqual((await self.client.get("/map")).status_code, 200)
        self.assertEqual(set(worker_threads), {"generate", "read", "write"})
        self.assertTrue(all(thread != loop_thread for thread in worker_threads.values()))

    async def test_get_returns_previous_map_while_generation_is_blocked(self):
        self.store.replace_map(self.graph)
        started, release = Event(), Event()

        def slow_generate():
            started.set()
            if not release.wait(5):
                raise RuntimeError("Worker was not released while GET completed")
            return MapData(source_segment_count=1)

        with patch.object(routes, "generate_map", side_effect=slow_generate):
            task = asyncio.create_task(self.client.post("/map/generate"))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                read = await asyncio.wait_for(self.client.get("/map"), timeout=2)
                self.assertEqual(read.status_code, 200)
                self.assertEqual(read.json(), self.graph.model_dump(mode="json"))
                self.assertFalse(task.done())
            finally:
                release.set()
                response = await task
        self.assertEqual(response.status_code, 200)

    async def test_post_uses_merged_timeline_generator_and_persists_its_result(self):
        text = "They discovered a cave east of the river."
        event = TimelineEvent(
            id="discovery", title="A cave", description=text, category="discovery",
            start_time=5, end_time=10, locations=["cave", "river"],
            source_segments=[TimelineSourceSegment(text=text, start_time=5, end_time=10)],
            created_at="2026-10-17", updated_at="2026-10-17",
        )
        # Keep the accepted generate_map() and extraction pipeline real; isolate
        # only the stored inputs and the heavyweight generic-word loader.
        with patch.object(map_generator, "load_timeline_events", return_value=[event]), \
             patch.object(map_generator, "load_transcript_documents", return_value=[]), \
             patch.object(map_generator, "_generic_location_words", return_value={"cave", "river"}):
            response = await self.client.post("/map/generate")
        self.assertEqual(response.status_code, 200)
        graph = MapData.model_validate(response.json())
        self.assertEqual({node.id for node in graph.nodes}, {"cave", "river"})
        self.assertEqual([(edge.source, edge.relation.value, edge.target) for edge in graph.edges],
                         [("cave", "east_of", "river")])
        self.assertEqual(graph.source_segment_count, 1)
        self.assertIsNotNone(graph.generated_at)
        self.assertEqual(MapStore(self.store.file_path).get_map(), graph)


class DefaultMapStoreTests(unittest.TestCase):
    def test_store_uses_backend_data_directory_without_writing(self):
        from app.core.config import settings

        with TemporaryDirectory() as directory:
            routes.get_map_store.cache_clear()
            self.addCleanup(routes.get_map_store.cache_clear)
            with patch.object(settings, "backend_root_path", directory):
                store = routes.get_map_store()
                self.assertIs(routes.get_map_store(), store)
            self.assertEqual(store.file_path, Path(directory) / "data/geographic_map.json")
            self.assertFalse(store.file_path.parent.exists())


if __name__ == "__main__":
    unittest.main()
