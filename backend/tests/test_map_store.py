"""Offline persistence regressions for the current geographic map model."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.base_models.map_models import MapData  # noqa: E402
from app.functions.geographic_mapping.map_store import MapStore  # noqa: E402


def populated_map():
    return MapData(
        nodes=[
            dict(id="waterdeep", name="Waterdeep", kind="named",
                 aliases=["the City of Splendors"], mentions=3,
                 first_seen=1.5, last_seen=30.0),
            dict(id="cave", name="Höhle", kind="generic", aliases=[],
                 mentions=2, first_seen=12.0, last_seen=25.5),
        ],
        edges=[
            dict(id="waterdeep:near:cave", source="waterdeep", target="cave",
                 relation="near", evidence="Waterdeep is near the Höhle.",
                 timestamp=12.0, confidence=0.9, count=2),
        ],
        source_segment_count=7,
        generated_at="2026-10-17T10:00:00+00:00",
    )


class MapStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.store = MapStore(self.directory / "map.json")

    def test_missing_map_is_empty_without_creating_directories_or_files(self):
        nested = self.directory / "not-created" / "map.json"
        store = MapStore(nested)
        self.assertFalse(nested.parent.exists())
        self.assertEqual(store.get_map(), MapData())
        self.assertFalse(nested.parent.exists())

    def test_populated_current_model_roundtrips_across_store_instances(self):
        graph = populated_map()
        returned = self.store.replace_map(graph)
        self.assertEqual(returned, graph)
        self.assertIsNot(returned, graph)
        reopened = MapStore(self.store.file_path)
        self.assertEqual(reopened.get_map().model_dump(mode="json"),
                         graph.model_dump(mode="json"))
        self.assertIn("Höhle", self.store.file_path.read_text(encoding="utf-8"))

    def test_replacing_map_creates_parent_and_replaces_previous_content(self):
        store = MapStore(self.directory / "nested" / "map.json")
        store.replace_map(populated_map())
        replacement = MapData(source_segment_count=1)
        self.assertEqual(store.replace_map(replacement), replacement)
        self.assertEqual(MapStore(store.file_path).get_map(), replacement)

    def test_clear_map_persists_a_valid_empty_map(self):
        self.store.replace_map(populated_map())
        self.assertEqual(self.store.clear_map(), MapData())
        self.assertEqual(MapStore(self.store.file_path).get_map(), MapData())

    def test_invalid_existing_data_is_reported_without_overwriting(self):
        for content in ("invalid json", '{"source_segment_count": -1}',
                        '{"nodes": [], "edges": [{"id": "broken", '
                        '"source": "missing", "target": "missing", "relation": "near"}]}'):
            with self.subTest(content=content):
                self.store.file_path.write_text(content, encoding="utf-8")
                before = self.store.file_path.read_bytes()
                with self.assertRaises(ValidationError):
                    self.store.get_map()
                self.assertEqual(self.store.file_path.read_bytes(), before)

    def test_invalid_replacement_preserves_previous_file(self):
        old = self.store.replace_map(populated_map())
        before = self.store.file_path.read_bytes()
        invalid = populated_map()
        # Models are mutable: storage must revalidate before replacing a file.
        invalid.edges[0].target = "unknown-node"
        with self.assertRaises(ValidationError):
            self.store.replace_map(invalid)
        self.assertEqual(self.store.file_path.read_bytes(), before)
        self.assertEqual(self.store.get_map(), old)

    def test_failed_atomic_write_preserves_map_and_cleans_temporary_file(self):
        old = self.store.replace_map(populated_map())
        before = self.store.file_path.read_bytes()
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                with patch(f"app.functions.geographic_mapping.map_store.os.{operation}",
                           side_effect=OSError("disk failure")):
                    with self.assertRaises(OSError):
                        self.store.replace_map(MapData(source_segment_count=3))
                self.assertEqual(self.store.file_path.read_bytes(), before)
                self.assertEqual(self.store.get_map(), old)
                self.assertEqual(list(self.directory.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
