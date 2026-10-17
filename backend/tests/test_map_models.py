"""Contract tests for the geographic map models (issue #46).

Pure Pydantic: no LLM, no embedding model, no network - so these are
deterministic and safe to run in CI.
"""

import json
from pathlib import Path
import sys
import unittest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError

from app.base_models.map_models import (
    LocationKind,
    MapData,
    MapEdge,
    MapGenerationResponse,
    MapNode,
    MapResponse,
    SpatialRelation,
    make_edge_id,
    make_node_id,
)

SAMPLE_PATH = BACKEND_DIR / "tests" / "data" / "map_sample.json"


class MapSampleTests(unittest.TestCase):
    """The shipped sample must always satisfy the contract."""

    def setUp(self):
        self.raw = json.loads(SAMPLE_PATH.read_text())

    def test_sample_round_trips(self):
        data = MapData.model_validate(self.raw)
        self.assertEqual(len(data.nodes), 7)
        self.assertEqual(len(data.edges), 4)
        self.assertEqual(data.source_segment_count, 9)
        self.assertIsNotNone(data.generated_at)

    def test_sample_edges_reference_existing_nodes(self):
        data = MapData.model_validate(self.raw)
        node_ids = {node.id for node in data.nodes}
        for edge in data.edges:
            self.assertIn(edge.source, node_ids)
            self.assertIn(edge.target, node_ids)

    def test_sample_ids_match_the_deterministic_rule(self):
        data = MapData.model_validate(self.raw)
        for node in data.nodes:
            self.assertEqual(node.id, make_node_id(node.name))
        for edge in data.edges:
            self.assertEqual(
                edge.id,
                make_edge_id(edge.source, edge.relation, edge.target),
            )

    def test_sample_covers_both_location_kinds_and_aliases(self):
        data = MapData.model_validate(self.raw)
        kinds = {node.kind for node in data.nodes}
        self.assertEqual(kinds, {LocationKind.named, LocationKind.generic})
        aliased = [node for node in data.nodes if node.aliases]
        self.assertTrue(aliased, "sample should show the alias case")


class DeterministicIdTests(unittest.TestCase):
    """Same place -> same node. This is what stops duplicate map nodes."""

    def test_same_name_gives_same_id_regardless_of_case_and_spacing(self):
        self.assertEqual(make_node_id("Castle Ravenwatch"), "castle-ravenwatch")
        self.assertEqual(make_node_id("  castle   ravenwatch "), "castle-ravenwatch")
        self.assertEqual(make_node_id("CASTLE-RAVENWATCH"), "castle-ravenwatch")

    def test_different_names_give_different_ids(self):
        self.assertNotEqual(make_node_id("Waterdeep"), make_node_id("Neverwinter"))

    def test_unusable_name_falls_back(self):
        self.assertEqual(make_node_id("!!!"), "unknown")

    def test_edge_id_is_stable_for_enum_and_string(self):
        self.assertEqual(
            make_edge_id("cave", SpatialRelation.east_of, "river"),
            make_edge_id("cave", "east_of", "river"),
        )


class ValidationTests(unittest.TestCase):
    """Constraints that protect downstream consumers."""

    def test_unknown_relation_is_rejected(self):
        with self.assertRaises(ValidationError):
            MapEdge(id="a:b:c", source="a", target="c", relation="beside")

    def test_empty_name_is_rejected(self):
        with self.assertRaises(ValidationError):
            MapNode(id="x", name="")

    def test_mentions_must_be_at_least_one(self):
        with self.assertRaises(ValidationError):
            MapNode(id="x", name="Cave", mentions=0)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(ValidationError):
            MapNode(id="x", name="Cave", first_seen=-1.0)

    def test_confidence_must_be_between_zero_and_one(self):
        with self.assertRaises(ValidationError):
            MapEdge(
                id="a:near:c", source="a", target="c",
                relation=SpatialRelation.near, confidence=1.5,
            )

    def test_confidence_may_be_omitted(self):
        edge = MapEdge(
            id="a:near:c", source="a", target="c",
            relation=SpatialRelation.near,
        )
        self.assertIsNone(edge.confidence)

    def test_defaults_give_an_empty_map(self):
        data = MapData()
        self.assertEqual(data.nodes, [])
        self.assertEqual(data.edges, [])
        self.assertEqual(data.source_segment_count, 0)
        self.assertIsNone(data.generated_at)


class ResponseContractTests(unittest.TestCase):
    """The API shapes the map endpoints implement."""

    def test_generation_response_extends_read_response(self):
        self.assertTrue(issubclass(MapGenerationResponse, MapResponse))

    def test_responses_can_be_built_from_map_data(self):
        data = MapData.model_validate(json.loads(SAMPLE_PATH.read_text()))

        read = MapResponse(
            nodes=data.nodes, edges=data.edges,
            total_nodes=len(data.nodes), total_edges=len(data.edges),
            generated_at=data.generated_at,
            source_segment_count=data.source_segment_count,
        )
        self.assertEqual(read.total_nodes, 7)

        generated = MapGenerationResponse(
            nodes=data.nodes, edges=data.edges,
            total_nodes=len(data.nodes), total_edges=len(data.edges),
            generated_at=data.generated_at,
            source_segment_count=data.source_segment_count,
        )
        self.assertEqual(generated.source_segment_count, 9)


class MapViewCompatibilityTests(unittest.TestCase):
    """
    The shipped map view validates every response and drops the whole thing if
    anything is unexpected, so the contract has to satisfy it exactly.
    """

    VIEW_RELATIONS = {
        "north_of", "south_of", "east_of", "west_of", "near",
        "inside", "contains", "connected_to", "travelled_to",
    }
    VIEW_NODE_FIELDS = {"id", "name", "mentions", "first_seen", "last_seen"}
    VIEW_EDGE_FIELDS = {"id", "source", "target", "relation", "evidence", "timestamp"}

    def test_relation_vocabulary_matches_the_view(self):
        self.assertEqual({r.value for r in SpatialRelation}, self.VIEW_RELATIONS)

    def test_both_responses_carry_the_fields_the_view_requires(self):
        # The view needs nodes, edges and source_segment_count on GET as well
        # as POST; a response missing any of them is discarded.
        for model in (MapResponse, MapGenerationResponse):
            with self.subTest(model=model.__name__):
                self.assertTrue(
                    {"nodes", "edges", "source_segment_count"}
                    <= set(model.model_fields)
                )

    def test_nodes_and_edges_carry_the_fields_the_view_requires(self):
        data = MapData.model_validate(json.loads(SAMPLE_PATH.read_text()))
        payload = MapResponse(
            nodes=data.nodes, edges=data.edges,
            source_segment_count=data.source_segment_count,
        ).model_dump(mode="json")

        for node in payload["nodes"]:
            self.assertTrue(self.VIEW_NODE_FIELDS <= set(node))
        for edge in payload["edges"]:
            self.assertTrue(self.VIEW_EDGE_FIELDS <= set(edge))
            self.assertIn(edge["relation"], self.VIEW_RELATIONS)


class ContractHardeningTests(unittest.TestCase):
    """Rules added after testing the contract against real extractor output."""

    def test_edge_count_tracks_repeated_traversals(self):
        edge = MapEdge(
            id="a:travelled_to:b", source="a", target="b",
            relation=SpatialRelation.travelled_to, count=3,
        )
        self.assertEqual(edge.count, 3)

    def test_edges_referencing_unknown_nodes_are_rejected(self):
        # Caught 4 orphan edges during development; now impossible to ship.
        with self.assertRaises(ValidationError):
            MapData(
                nodes=[MapNode(id="cave", name="cave")],
                edges=[MapEdge(
                    id="cave:near:river", source="cave", target="river",
                    relation=SpatialRelation.near,
                )],
            )

    def test_scoped_ids_separate_same_named_places(self):
        self.assertNotEqual(
            make_node_id("tower", scope="Kraghammer"),
            make_node_id("tower", scope="Waterdeep"),
        )
        self.assertEqual(make_node_id("tower", scope="Kraghammer"), "kraghammer:tower")


if __name__ == "__main__":
    unittest.main()
