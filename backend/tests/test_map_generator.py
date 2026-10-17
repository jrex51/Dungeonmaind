"""Map generation tests (issue #48).

Timeline events, transcript documents, the relation validator and the generic
place words are all passed in, so the pipeline runs offline: no Ollama, no
ChromaDB, no sentence-transformers, and nothing patched into sys.modules.
"""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.base_models.map_models import LocationKind, SpatialRelation  # noqa: E402
from app.base_models.timeline_models import (  # noqa: E402
    TimelineEvent,
    TimelineSourceSegment,
)
from app.functions.geographic_mapping import map_generator  # noqa: E402
from app.functions.geographic_mapping.map_generator import (  # noqa: E402
    location_kind,
)


GENERIC = {"cave", "river", "tavern", "castle", "forest", "bridge"}


def event(event_id, category, start, end, locations, text, title="Event"):
    return TimelineEvent(
        id=event_id,
        title=title,
        description=text,
        category=category,
        start_time=start,
        end_time=end,
        locations=locations,
        source_segments=[TimelineSourceSegment(text=text, start_time=start, end_time=end)],
        created_at="2026-10-08T00:00:00+00:00",
        updated_at="2026-10-08T00:00:00+00:00",
    )


class FakeDocument:
    def __init__(self, text, start, end):
        self.page_content = text
        self.metadata = {"start_time": start, "end_time": end, "source": "transcriptions"}


EVENTS = [
    event("e1", "travel", 0.0, 10.0, ["Waterdeep", "Blackwood Forest"],
          "The party left Waterdeep at dawn and travelled toward Blackwood Forest."),
    event("e2", "discovery", 10.0, 20.0, ["cave", "river"],
          "They discovered a cave east of the river."),
    event("e3", "travel", 20.0, 30.0, ["tavern", "Castle Ravenwatch"],
          "Later they reached the tavern near Castle Ravenwatch."),
    event("e4", "dialogue", 30.0, 40.0, ["the castle"],
          "Back at the castle, the guards were waiting."),
]

TRANSCRIPT = [FakeDocument(e.description, e.start_time, e.end_time) for e in EVENTS]


def no_relation(text, place_a, place_b):
    return "NONE"


def generate(events=EVENTS, documents=TRANSCRIPT, llm=no_relation):
    return map_generator.generate_map(
        events=events, documents=documents, relation_llm=llm, generic_words=GENERIC
    )


def edge_set(data, relation):
    return {(e.source, e.target) for e in data.edges if e.relation == relation}


class NodeTests(unittest.TestCase):
    def test_nodes_come_from_timeline_locations(self):
        names = {node.name for node in generate().nodes}
        self.assertTrue({"Waterdeep", "Blackwood Forest", "cave", "river"} <= names)

    def test_generic_name_merges_into_the_named_place(self):
        data = generate()
        ids = {node.id for node in data.nodes}
        self.assertIn("castle-ravenwatch", ids)
        self.assertNotIn("the-castle", ids)

        ravenwatch = next(n for n in data.nodes if n.id == "castle-ravenwatch")
        self.assertIn("the castle", ravenwatch.aliases)
        self.assertEqual(ravenwatch.mentions, 2)

    def test_timestamps_come_from_the_events(self):
        ravenwatch = next(n for n in generate().nodes if n.id == "castle-ravenwatch")
        self.assertEqual(ravenwatch.first_seen, 20.0)
        self.assertEqual(ravenwatch.last_seen, 40.0)

    def test_kinds(self):
        by_id = {node.id: node for node in generate().nodes}
        self.assertEqual(by_id["waterdeep"].kind, LocationKind.named)
        self.assertEqual(by_id["cave"].kind, LocationKind.generic)

    def test_kind_reads_past_the_article_and_capitalised_generic_words(self):
        # The old capitalisation check read the first letter only.
        self.assertEqual(location_kind("the Greyspine Mines", GENERIC), LocationKind.named)
        self.assertEqual(location_kind("Tavern", GENERIC), LocationKind.generic)
        self.assertEqual(location_kind("the old bridge", GENERIC), LocationKind.generic)


class RelationTests(unittest.TestCase):
    def test_stated_relation_is_read_from_the_transcript(self):
        east = [e for e in generate().edges if e.relation == SpatialRelation.east_of]
        self.assertEqual(len(east), 1)
        self.assertEqual((east[0].source, east[0].target), ("cave", "river"))
        self.assertIn("east of the river", east[0].evidence)

    def test_relation_stated_just_outside_the_event_is_found(self):
        events = [event("n1", "dialogue", 50.0, 58.0, ["Neverwinter", "Waterdeep"],
                        "They argue about Neverwinter and Waterdeep for a while.")]
        documents = [
            FakeDocument("They argue about Neverwinter and Waterdeep for a while.", 50.0, 58.0),
            FakeDocument("Neverwinter lies north of Waterdeep, the DM explains.", 58.5, 70.0),
        ]
        data = generate(events, documents)
        self.assertIn(("neverwinter", "waterdeep"), edge_set(data, SpatialRelation.north_of))

    def test_event_source_segments_are_used_without_a_transcript(self):
        data = generate(documents=[])
        self.assertIn(("cave", "river"), edge_set(data, SpatialRelation.east_of))

    def test_validator_decides_sentences_without_a_cue(self):
        events = [event("v1", "discovery", 0.0, 5.0, ["watchtower", "harbour"],
                        "The watchtower overlooks the harbour from the cliffs.")]

        def llm(text, place_a, place_b):
            return "near"

        data = generate(events, [], llm)
        self.assertIn(("watchtower", "harbour"), edge_set(data, SpatialRelation.near))

    def test_validator_is_not_asked_about_cue_sentences(self):
        asked = []

        def spy(text, place_a, place_b):
            asked.append(text)
            return "NONE"

        generate(llm=spy)
        self.assertFalse(any("east of the river" in text for text in asked))

    def test_one_fact_phrased_both_ways_is_one_edge(self):
        events = [
            event("a1", "discovery", 0.0, 5.0, ["Neverwinter", "Waterdeep"],
                  "Neverwinter lies north of Waterdeep."),
            event("a2", "discovery", 10.0, 15.0, ["Neverwinter", "Waterdeep"],
                  "Waterdeep sits south of Neverwinter."),
        ]
        relations = [e for e in generate(events, []).edges
                     if e.relation != SpatialRelation.travelled_to]
        self.assertEqual(len(relations), 1)
        self.assertEqual(
            (relations[0].source, relations[0].relation, relations[0].target),
            ("neverwinter", SpatialRelation.north_of, "waterdeep"),
        )
        self.assertEqual(relations[0].count, 2)

    def test_conflicting_descriptions_keep_the_most_repeated(self):
        events = [
            event("c1", "discovery", 0.0, 5.0, ["shrine", "grove"], "The shrine is near the grove."),
            event("c2", "discovery", 10.0, 15.0, ["shrine", "grove"], "The shrine stands inside the grove."),
            event("c3", "discovery", 20.0, 25.0, ["shrine", "grove"], "The shrine lies inside the grove."),
        ]
        relations = {e.relation for e in generate(events, []).edges}
        self.assertEqual(relations, {SpatialRelation.inside})


class JourneyTests(unittest.TestCase):
    def test_journey_follows_travel_events_only(self):
        journeys = edge_set(generate(), SpatialRelation.travelled_to)
        self.assertIn(("waterdeep", "blackwood-forest"), journeys)
        self.assertIn(("blackwood-forest", "tavern"), journeys)
        # The cave scene is a discovery, not a journey.
        self.assertNotIn(("river", "tavern"), journeys)

    def test_movement_phrasing_outside_travel_events_is_not_a_journey(self):
        text = "The road from Waterdeep to Neverwinter was closed by the guard."
        events = [event("r1", "dialogue", 0.0, 5.0, ["Waterdeep", "Neverwinter"], text)]
        data = generate(events, [FakeDocument(text, 0.0, 5.0)])
        self.assertEqual(edge_set(data, SpatialRelation.travelled_to), set())

    def test_two_names_for_one_spot_are_not_a_trip(self):
        # From the end-to-end run: the timeline listed both "Waterdeep" and the
        # transcription slip "Waterdeep Adorn" for the same sentence.
        events = [
            event("w1", "travel", 0.0, 8.0, ["Waterdeep Adorn", "Waterdeep"],
                  "The party left Waterdeep Adorn and travelled from Waterdeep along the coast road."),
            event("w2", "travel", 26.0, 29.0, ["Fandolin"],
                  "The party travelled onward and reached Fandolin."),
        ]
        journeys = edge_set(generate(events, []), SpatialRelation.travelled_to)
        self.assertEqual(journeys, {("waterdeep", "fandolin")})

    def test_stated_movement_beats_text_order(self):
        text = "They arrived in Neverwinter after the ride from Waterdeep to Neverwinter."
        events = [event("j1", "travel", 0.0, 5.0, ["Neverwinter", "Waterdeep"], text)]
        journeys = edge_set(generate(events, [FakeDocument(text, 0.0, 5.0)]),
                            SpatialRelation.travelled_to)
        self.assertEqual(journeys, {("waterdeep", "neverwinter")})


class ContractTests(unittest.TestCase):
    def test_every_edge_references_a_real_node(self):
        data = generate()
        ids = {node.id for node in data.nodes}
        for edge in data.edges:
            self.assertIn(edge.source, ids)
            self.assertIn(edge.target, ids)

    def test_generation_is_stamped_and_counts_events(self):
        data = generate()
        self.assertIsNotNone(data.generated_at)
        self.assertEqual(data.source_segment_count, 4)

    def test_empty_timeline_gives_an_empty_map_without_reading_the_transcript(self):
        with patch.object(map_generator, "load_transcript_documents",
                          side_effect=AssertionError("transcript must not be read")):
            data = map_generator.generate_map(events=[], relation_llm=no_relation,
                                              generic_words=GENERIC)
        self.assertEqual((data.nodes, data.edges, data.source_segment_count), ([], [], 0))


if __name__ == "__main__":
    unittest.main()
