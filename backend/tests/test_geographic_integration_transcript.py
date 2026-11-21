"""Exercise offline timeline location extraction and map generation on D&D dialogue."""

import json
from pathlib import Path
import unittest

from test_map_generator import FakeDocument, edge_set, event, generate
from test_timeline_grounding import load_generator

from app.base_models.map_models import LocationKind, SpatialRelation
from app.base_models.timeline_models import TimelineSourceSegment
from app.functions.geographic_mapping.map_sources import split_sentences


DATA = Path(__file__).parent / "data"


class GeographicTranscriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.timeline = load_generator()

    def test_short_recording_recovers_the_innkeepers_direction(self):
        # The stored transcription documents keep punctuation that the timeline
        # source segments can lose when split at clause boundaries.
        rows = json.loads((DATA / "dnd_geographic_recording.json").read_text(encoding="utf-8"))
        documents = [FakeDocument(text, start, end) for start, end, text in rows]
        events = []
        for group_start, group_end in ((0, 49), (49, 73), (102, 112)):
            group = [
                TimelineSourceSegment(text=text, speaker="DM", start_time=start, end_time=end)
                for start, end, text in rows if group_start <= start < group_end
            ]
            events.append(self.timeline._create_event_from_group(group))

        self.assertEqual([(e.category.value, e.locations) for e in events], [
            ("travel", ["River Watch", "Stonebridge"]),
            ("combat", ["Broken Watch tower"]),
            ("rest", ["Stonebridge"]),
        ])

        graph = generate(events, documents)
        nodes = {node.name: node for node in graph.nodes}
        self.assertEqual(set(nodes), {"River Watch", "Stonebridge", "Broken Watch tower"})
        self.assertEqual(nodes["River Watch"].aliases, ["Riverwatch"])
        self.assertEqual(nodes["Stonebridge"].aliases, [])
        self.assertEqual(nodes["Stonebridge"].mentions, 2)
        self.assertTrue(all(node.kind == LocationKind.named for node in graph.nodes))
        edges = {edge.id: edge for edge in graph.edges}
        self.assertEqual(set(edges), {
            "stonebridge:north_of:river-watch", "river-watch:travelled_to:stonebridge",
        })
        direction = edges["stonebridge:north_of:river-watch"]
        self.assertEqual(direction.evidence, "The innkeeper tells you, Stonebridge is north of Riverwatch.")
        self.assertEqual(direction.timestamp, 18.32)
        travel = edges["river-watch:travelled_to:stonebridge"]
        self.assertEqual((travel.evidence, travel.count), ("We travel from River Watch to Stonebridge.", 1))

    def test_existing_transcript_geography(self):
        text = (DATA / "dnd_temporal_integration_transcript.txt").read_text(encoding="utf-8")
        excerpts = [
            next(sentence for sentence in split_sentences(text) if sentence.startswith(prefix))
            for prefix in ("They discovered a cave", "Later that evening", "On the 12th of Eleasis")
        ]
        locations = [self.timeline._extract_event_entities(sentence, ["DM"])[1] for sentence in excerpts]
        self.assertEqual(locations, [["cave", "river"], ["village", "castle"], ["Castle Ravenwatch"]])

        events = [
            event(str(index), category, index * 10, index * 10 + 5, places, sentence)
            for index, (category, places, sentence) in enumerate(
                zip(("discovery", "travel", "travel"), locations, excerpts)
            )
        ]
        graph = generate(events, documents=[])
        self.assertEqual({node.name for node in graph.nodes},
                         {"cave", "river", "village", "Castle Ravenwatch"})
        castle = next(node for node in graph.nodes if node.name == "Castle Ravenwatch")
        self.assertEqual((castle.aliases, castle.mentions), (["castle"], 2))
        self.assertEqual({(e.source, e.relation, e.target) for e in graph.edges}, {
            ("cave", SpatialRelation.east_of, "river"),
            ("village", SpatialRelation.near, "castle-ravenwatch"),
            ("village", SpatialRelation.travelled_to, "castle-ravenwatch"),
        })

    def test_travel_event_does_not_turn_a_plan_or_denial_into_a_trip(self):
        # An optional validator may try to supply a link missed by the cue rules.
        def validator(_text, source, _target):
            return "travelled_to" if source == "River Watch" else "NONE"

        for sentence in (
            "We could travel from River Watch to Stonebridge tomorrow, but not today.",
            "We didn’t actually travel from River Watch to Stonebridge.",
            "We didn't go to Stonebridge, but we arrived at River Watch.",
            "We arrived at River Watch. We plan to travel to Stonebridge tomorrow.",
        ):
            with self.subTest(sentence=sentence):
                events = [event("travel", "travel", 0, 5, ["River Watch", "Stonebridge"], sentence)]
                documents = [FakeDocument(sentence, 0, 5)]
                graph = generate(events, documents)
                self.assertEqual(edge_set(graph, SpatialRelation.travelled_to), set())

                graph = generate(events, documents, llm=validator)
                self.assertEqual(edge_set(graph, SpatialRelation.travelled_to), set())

    def test_legacy_events_with_both_spellings_share_a_node(self):
        for spelling in ("Riverwatch", "River Watch"):
            with self.subTest(spelling=spelling):
                events = [
                    event("travel", "travel", 0, 5, ["River Watch", "Stonebridge"],
                          "We travel from River Watch to Stonebridge."),
                    event("directions", "dialogue", 10, 15, ["Stonebridge", "Riverwatch"],
                          f"Stonebridge is north of {spelling}."),
                ]
                graph = generate(events, documents=[])
                river_watch = next(node for node in graph.nodes if node.name == "River Watch")
                self.assertEqual((river_watch.aliases, river_watch.mentions), (["Riverwatch"], 2))
                self.assertEqual({node.id for node in graph.nodes}, {"river-watch", "stonebridge"})
                self.assertEqual(edge_set(graph, SpatialRelation.north_of), {("stonebridge", "river-watch")})


if __name__ == "__main__":
    unittest.main()
