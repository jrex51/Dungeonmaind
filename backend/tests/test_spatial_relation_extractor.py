"""Spatial relation tests (issue #47). Deterministic: no model server is used."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.base_models.map_models import SpatialRelation
from app.functions.geographic_mapping import spatial_relation_extractor
from app.functions.geographic_mapping.spatial_relation_extractor import (
    adjacent_pairs,
    extract_cue_relations,
    extract_relations,
    parse_validator_answer,
)


def answers(table, default="NONE"):
    """A fake validator: {(place_a, place_b): answer}, recording every call."""

    calls = []

    def llm(text, place_a, place_b):
        calls.append((place_a, place_b))
        return table.get((place_a, place_b), default)

    llm.calls = calls
    return llm


class IssueExamplesTests(unittest.TestCase):
    """The four examples written into issue #47, with no model running."""

    def test_issue_examples(self):
        cases = [
            ("The village is north of Neverwinter.", ["village", "Neverwinter"],
             False, ("village", SpatialRelation.north_of, "Neverwinter")),
            ("The ruined temple lies inside the forest.", ["ruined temple", "forest"],
             False, ("ruined temple", SpatialRelation.inside, "forest")),
            ("The old bridge is near Waterdeep.", ["old bridge", "Waterdeep"],
             False, ("old bridge", SpatialRelation.near, "Waterdeep")),
            ("We travelled from Waterdeep to Neverwinter.", ["Waterdeep", "Neverwinter"],
             True, ("Waterdeep", SpatialRelation.travelled_to, "Neverwinter")),
        ]
        for sentence, places, travel, expected in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual(
                    extract_cue_relations(sentence, places, allow_travel=travel),
                    [expected],
                )


class CueRelationTests(unittest.TestCase):
    """Direction comes from word order, which is what a model kept inverting."""

    cases = [
        ("They discovered a cave east of the river and decided to rest inside.",
         ["cave", "river"], ("cave", SpatialRelation.east_of, "river")),
        ("Later that evening, they reached a village near the castle.",
         ["village", "castle"], ("village", SpatialRelation.near, "castle")),
        ("Three hours later, they reached an old bridge beside the river.",
         ["old bridge", "river"], ("old bridge", SpatialRelation.near, "river")),
        ("The shrine sits within the temple grounds.",
         ["shrine", "temple grounds"], ("shrine", SpatialRelation.inside, "temple grounds")),
    ]

    def test_direction_follows_word_order(self):
        for sentence, places, expected in self.cases:
            with self.subTest(sentence=sentence[:40]):
                self.assertEqual(extract_cue_relations(sentence, places), [expected])

    def test_movement_with_left_and_toward(self):
        self.assertEqual(
            extract_cue_relations("They left Kraghammer toward the Greyspine Mines.",
                                  ["Kraghammer", "Greyspine Mines"], allow_travel=True),
            [("Kraghammer", SpatialRelation.travelled_to, "Greyspine Mines")],
        )

    def test_movement_direction_comes_from_markers_not_mention_order(self):
        cases = [
            ("We made it back to the tavern after leaving Greyspine Manor.",
             ["tavern", "Greyspine Manor"], ("Greyspine Manor", "tavern")),
            ("They arrived in Neverwinter after the ride from Waterdeep to Neverwinter.",
             ["Neverwinter", "Waterdeep"], ("Waterdeep", "Neverwinter")),
        ]
        for sentence, places, (origin, destination) in cases:
            with self.subTest(sentence=sentence[:40]):
                self.assertEqual(
                    extract_cue_relations(sentence, places, allow_travel=True),
                    [(origin, SpatialRelation.travelled_to, destination)],
                )

    def test_movement_phrasing_is_ignored_outside_travel_events(self):
        # A road between two places is not a journey.
        self.assertEqual(
            extract_cue_relations("The road from Waterdeep to Neverwinter was closed.",
                                  ["Waterdeep", "Neverwinter"]),
            [],
        )

    def test_distant_cue_is_not_attached_to_far_places(self):
        # "north of" belongs to "the road"/"the city", not to the two places.
        sentence = ("The party left Waterdeep at dawn and followed the road "
                    "north of the city toward Blackwood Forest.")
        places = ["Waterdeep", "Blackwood Forest"]

        self.assertEqual(extract_cue_relations(sentence, places), [])

        # In a travel event the movement is real and is picked up - but still
        # no positional relation links the two far-apart places.
        self.assertEqual(
            extract_cue_relations(sentence, places, allow_travel=True),
            [("Waterdeep", SpatialRelation.travelled_to, "Blackwood Forest")],
        )

    def test_containment_as_transcripts_phrase_it(self):
        # None of these use "inside" or "within"; all are from real CRD3 lines.
        cases = [
            ("I hail from a town called Ty'rex, located in the heart of Draconia.",
             ["Ty'rex", "Draconia"], ("Ty'rex", SpatialRelation.inside, "Draconia")),
            ("the Greyspine Mines at the bottom of Kraghammer",
             ["Greyspine Mines", "Kraghammer"],
             ("Greyspine Mines", SpatialRelation.inside, "Kraghammer")),
            ("this gargantuan crevasse in the Underdark",
             ["gargantuan crevasse", "Underdark"],
             ("gargantuan crevasse", SpatialRelation.inside, "Underdark")),
            ("Cliffkeep Mountains proper, surrounding Kraghammer",
             ["Cliffkeep Mountains", "Kraghammer"],
             ("Cliffkeep Mountains", SpatialRelation.contains, "Kraghammer")),
        ]
        for sentence, places, expected in cases:
            with self.subTest(sentence=sentence[:40]):
                self.assertEqual(extract_cue_relations(sentence, places), [expected])

    def test_a_passage_between_places_is_a_connection(self):
        self.assertEqual(
            extract_cue_relations(
                "the stone carved tunnel that leads into the city proper",
                ["stone carved tunnel", "city proper"]),
            [("stone carved tunnel", SpatialRelation.connected_to, "city proper")],
        )

    def test_of_is_containment_only_for_a_part(self):
        # "the walls of the cavern" is containment...
        self.assertEqual(
            extract_cue_relations("elements embedded in the walls of the cavern ahead",
                                  ["walls", "cavern"]),
            [("walls", SpatialRelation.inside, "cavern")],
        )
        # ...but "the city of Kraghammer" is one place named twice, not two.
        self.assertEqual(
            extract_cue_relations("the Ironkeeper of the entire city of Kraghammer",
                                  ["city", "Kraghammer"]),
            [],
        )

    def test_cue_does_not_bind_across_a_clause(self):
        # Without the clause guard the second "in" reaches back to Echo Park
        # and claims one city is inside the other.
        self.assertEqual(
            extract_cue_relations("There is one in Echo Park and one in Mar Vista.",
                                  ["Echo Park", "Mar Vista"]),
            [],
        )

    def test_in_front_of_is_not_containment(self):
        self.assertEqual(
            extract_cue_relations("the umber hulk in front of you",
                                  ["umber hulk", "front"]),
            [],
        )

    def test_a_negated_cue_states_nothing(self):
        for sentence in ("The shrine is not in the forest.",
                         "The mill isn't near the river.",
                         "The mill is not really near the river."):
            with self.subTest(sentence=sentence):
                places = ["shrine", "forest"] if "shrine" in sentence else ["mill", "river"]
                self.assertEqual(extract_cue_relations(sentence, places), [])

    def test_a_negated_trip_is_not_a_trip(self):
        self.assertEqual(
            extract_cue_relations("We didn't go from Waterdeep to Neverwinter.",
                                  ["Waterdeep", "Neverwinter"], allow_travel=True),
            [],
        )

    def test_single_place_yields_nothing(self):
        self.assertEqual(
            extract_cue_relations("bandits near the harbour", ["harbour"]), []
        )

    def test_unmapped_cue_is_ignored_not_guessed(self):
        self.assertEqual(
            extract_cue_relations("The tower stood behind the temple.",
                                  ["tower", "temple"]), []
        )


class ValidatorParsingTests(unittest.TestCase):
    def test_leading_value_wins(self):
        self.assertEqual(parse_validator_answer("NONE (not inside)"), "NONE")
        self.assertEqual(parse_validator_answer(" north_of\n"), "north_of")

    def test_anything_outside_the_set_is_none(self):
        self.assertEqual(parse_validator_answer("across_from"), "NONE")
        self.assertEqual(parse_validator_answer(""), "NONE")
        self.assertEqual(parse_validator_answer(None), "NONE")

    def test_pairs_are_neighbours_in_text_order(self):
        self.assertEqual(
            adjacent_pairs("From the docks past the market to the keep.",
                           ["keep", "docks", "market"]),
            [("docks", "market"), ("market", "keep")],
        )


class ValidatorTierTests(unittest.TestCase):
    """Tier 2 is injectable, so tests never touch a model server."""

    SENTENCE = "The watchtower overlooks the harbour from the cliffs."

    def test_cue_match_skips_the_model_entirely(self):
        def explode(*args):
            raise AssertionError("tier 2 must not run when a cue matched")

        out = extract_relations(
            {0: ("a cave east of the river", ["cave", "river"])}, llm=explode
        )
        self.assertEqual(out[0], [("cave", SpatialRelation.east_of, "river")])

    def test_symmetric_answer_becomes_a_relation(self):
        llm = answers({("watchtower", "harbour"): "near"})
        out = extract_relations({0: (self.SENTENCE, ["watchtower", "harbour"])}, llm=llm)
        self.assertEqual(out[0], [("watchtower", SpatialRelation.near, "harbour")])
        self.assertEqual(llm.calls, [("watchtower", "harbour")])

    def test_none_and_other_produce_no_relation(self):
        for reply in ("NONE", "other"):
            with self.subTest(reply=reply):
                out = extract_relations(
                    {0: (self.SENTENCE, ["watchtower", "harbour"])},
                    llm=answers({}, default=reply),
                )
                self.assertEqual(out, {})

    def test_directional_answer_kept_when_reverse_agrees(self):
        sentence = "The watchtower rises from the northern cliffs above the harbour."
        llm = answers({("watchtower", "harbour"): "north_of",
                       ("harbour", "watchtower"): "south_of"})
        out = extract_relations({0: (sentence, ["watchtower", "harbour"])}, llm=llm)
        self.assertEqual(out[0], [("watchtower", SpatialRelation.north_of, "harbour")])

    def test_compass_answer_needs_a_compass_word(self):
        # A compass answer with no compass word in the sentence is invented.
        llm = answers({("watchtower", "harbour"): "west_of",
                       ("harbour", "watchtower"): "east_of"})
        out = extract_relations({0: (self.SENTENCE, ["watchtower", "harbour"])}, llm=llm)
        self.assertEqual(out, {})

    def test_directional_answer_dropped_when_model_ignores_order(self):
        # The same answer whichever way round it is asked means order was ignored.
        llm = answers({("watchtower", "harbour"): "inside",
                       ("harbour", "watchtower"): "inside"})
        out = extract_relations({0: (self.SENTENCE, ["watchtower", "harbour"])}, llm=llm)
        self.assertEqual(out, {})

    def test_reverse_movement_is_found_in_travel_events(self):
        # No origin/destination marker here, so tier 1 cannot read the direction.
        sentence = "The tavern was our next stop once Greyspine Manor was behind us."
        places = ["tavern", "Greyspine Manor"]
        llm = answers({("Greyspine Manor", "tavern"): "travelled_to"})

        out = extract_relations({0: (sentence, places)}, llm=llm, travel={0})
        self.assertEqual(
            out[0], [("Greyspine Manor", SpatialRelation.travelled_to, "tavern")]
        )

        # Outside a travel event the reverse question is never asked.
        quiet = answers({("Greyspine Manor", "tavern"): "travelled_to"})
        self.assertEqual(extract_relations({0: (sentence, places)}, llm=quiet), {})
        self.assertEqual(quiet.calls, [("tavern", "Greyspine Manor")])

    def test_model_failure_degrades_quietly_and_stops(self):
        calls = []

        def broken(*args):
            calls.append(args)
            raise RuntimeError("no model server")

        out = extract_relations(
            {0: (self.SENTENCE, ["watchtower", "harbour"]),
             1: ("The mill stands by the old ford.", ["mill", "old ford"])},
            llm=broken,
        )
        self.assertEqual(out, {})
        self.assertEqual(len(calls), 1)

    def test_validator_calls_are_capped(self):
        llm = answers({})
        with patch.object(spatial_relation_extractor, "MAP_AI_MAX_PAIRS", 1):
            extract_relations(
                {0: (self.SENTENCE, ["watchtower", "harbour"]),
                 1: ("The mill stands by the old ford.", ["mill", "old ford"])},
                llm=llm,
            )
        self.assertEqual(len(llm.calls), 1)


if __name__ == "__main__":
    unittest.main()
