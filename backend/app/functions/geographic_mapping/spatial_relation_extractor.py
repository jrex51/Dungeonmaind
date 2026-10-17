"""Extract spatial relations between known locations (Release 3, issue #47).

The locations themselves come from the timeline; this module only decides how
two of them relate, in two tiers.

1. Cue matching, always on and deterministic. A cue phrase is matched against
   the sentence and the direction is taken from word order, so "a cave east of
   the river" gives cave east_of river.

   The cue vocabulary follows how sessions are actually spoken rather than how
   a textbook would phrase it: transcripts say "located in the heart of", "at
   the bottom of", "the walls of the cavern" and "a tunnel that leads into the
   city" far more often than "inside" or "within".

   Four guards keep that breadth from over-firing, each one earning its place
   against a sentence that fooled an earlier version:
     - proximity: a cue only binds to places sitting close to it, so it cannot
       reach across half a sentence;
     - clause boundaries: a cue may not cross "and" or "or", which stopped
       "one in Echo Park and one in Mar Vista" claiming one city is inside
       the other;
     - NOT_CONTAINMENT_AFTER_IN: "the umber hulk in front of you" is not
       containment;
     - "of" counts only for a part ("the walls of the cavern"), never for
       apposition, so "the city of Kraghammer" stays one place;
     - negation: "Balgus is not in the tavern" states nothing.

   Movement is read from the word in front of each place - "from"/"leaving"
   marks the origin, "to"/"reached" the destination - so "back to the tavern
   after leaving Greyspine Manor" runs Manor -> tavern. It is only tried for
   travel events, because elsewhere it over-fires on sentences like "the road
   from Waterdeep to Neverwinter was closed".

2. An LLM validator, off by default. Given one pair of places in one sentence
   it must answer a single SpatialRelation, NON_MAP_RELATION, or NONE. It is
   disabled because on the sentences the cue tier cannot resolve it produced
   more wrong relations than right ones, and because the models tested invent
   compass directions and relate people to places. Its guards - a reverse
   question for directional answers, and requiring a compass word in the
   sentence before accepting a compass answer - stay with it, since they are
   what kept the damage low. Set MAP_AI_ENABLED=1, and MAP_AI_MODEL to choose
   a model, to try it again after changing the prompt or the model.

Precision here is bounded by the location list the timeline supplies: most
remaining wrong edges come from entries that are not places at all, such as
"dwarves near table", not from the cues themselves.
"""

import json
import os
import re
import urllib.request

from app.base_models.map_models import SpatialRelation


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Off by default; see the module docstring for why. Opt in with
# MAP_AI_ENABLED=1.
MAP_AI_ENABLED = os.getenv("MAP_AI_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on",
}

MAP_AI_TIMEOUT = float(os.getenv("MAP_AI_TIMEOUT", "120"))

# Empty means "use the model selected in the app's settings".
MAP_AI_MODEL = os.getenv("MAP_AI_MODEL", "").strip()

# Upper bound on validator calls per generation, so a very long session cannot
# turn one map rebuild into hours of model time.
MAP_AI_MAX_PAIRS = int(os.getenv("MAP_AI_MAX_PAIRS", "400"))

# Maximum characters between a place and the cue. Correct readings keep the
# place close to the cue, but real speech pads it ("leads off into a few other
# underground rivers"), so the clause guard below does the real work and this
# only stops a cue reaching across half a sentence.
MAX_CUE_GAP = 26

# Even inside that gap the cue must not reach across a clause boundary. Without
# this, "There is one in Echo Park and one in Mar Vista" binds the second "in"
# back to Echo Park and claims one city is inside the other.
CLAUSE_BREAK = re.compile(r"\b(?:and|or|but|then|while|after|before|because|so)\b|[.;:!?]")

# A cue that is negated states the opposite: "Balgus is not in the tavern".
# Checked on the few words just before the cue (one word may sit between, as
# in "not really near"), and on trip markers ("we never left Waterdeep").
NEGATED_BEFORE = re.compile(r"(?:\b(?:not|never|no\s+longer|nowhere)|n't)\s+(?:[a-z']+\s+)?$")


def _negated(lowered: str, position: int) -> bool:
    return bool(NEGATED_BEFORE.search(lowered[max(0, position - 30):position]))


# "in" starts several phrases that are not containment at all. Without this,
# "the umber hulk in front of you" reads as the hulk being inside a place
# called "front".
NOT_CONTAINMENT_AFTER_IN = re.compile(
    r"^\s+(?:front|back|the\s+direction|the\s+way|charge|search|terms|order|"
    r"spite|addition|fact|case|part|between)\b"
)

# "A of B" is containment only when A is a part of something ("the walls of the
# cavern", "the entrance of the war camp"). It is apposition when A is a
# settlement word - "the city of Kraghammer" is one place, not two.
PART_WORDS = {
    "entrance", "entrances", "exit", "exits", "wall", "walls", "center",
    "centre", "edge", "edges", "side", "sides", "bottom", "top", "floor",
    "ceiling", "cavern", "caverns", "level", "levels", "ring", "portion",
    "portions", "part", "parts", "heart", "base", "rear", "interior",
    "outskirts", "remains", "mouth", "end", "corner", "corners", "depths",
}

# Order is priority: the first cue that binds to a place on each side wins, so
# specific phrases come before the general ones they contain.
CUES: list[tuple[str, SpatialRelation]] = [
    ("north of", SpatialRelation.north_of),
    ("south of", SpatialRelation.south_of),
    ("east of", SpatialRelation.east_of),
    ("west of", SpatialRelation.west_of),
    # Containment as transcripts phrase it: stated relations are
    # overwhelmingly "A is somewhere in B", rarely "inside" or "within".
    ("in the heart of", SpatialRelation.inside),
    ("in the middle of", SpatialRelation.inside),
    ("in the centre of", SpatialRelation.inside),
    ("in the center of", SpatialRelation.inside),
    ("at the bottom of", SpatialRelation.inside),
    ("at the top of", SpatialRelation.inside),
    ("located in", SpatialRelation.inside),
    ("surrounded by", SpatialRelation.inside),
    ("surrounding", SpatialRelation.contains),
    ("inside", SpatialRelation.inside),
    ("within", SpatialRelation.inside),
    ("contains", SpatialRelation.contains),
    ("connected to", SpatialRelation.connected_to),
    ("leads to", SpatialRelation.connected_to),
    ("next to", SpatialRelation.near),
    ("close to", SpatialRelation.near),
    ("beside", SpatialRelation.near),
    ("near", SpatialRelation.near),
    # A passage between two places, as transcripts phrase it: "the tunnel that
    # leads into the city", "a pool that spills off into the rivers". "go" is
    # deliberately absent: it describes people and limbs moving ("a dwarven
    # hand go straight to its forehead") as often as it describes a path.
    (r"\b(?:leads?|opens?|runs?|connects?|continues?|spills?|empties|"
     r"descends?|climbs?)\b[^.;:!?]{0,24}?\b(?:in|on)?to(?:wards?)?\b",
     SpatialRelation.connected_to),
    # Bare "in" is last: it is the most common containment word in real play
    # but also the loosest, so every phrase above gets first refusal. The
    # guards are what make it safe - it only binds when a place sits close on
    # each side ("the Mart in Echo Park"), not across a clause ("spit in the
    # direction of any dwarf in the city ... under the dungeon").
    ("in", SpatialRelation.inside),
    # Checked last and only for part-of words (see PART_WORDS).
    ("of", SpatialRelation.inside),
]

# Entries whose text is already a regex rather than a literal phrase.
_REGEX_CUES = {cue for cue, _ in CUES if cue.startswith(r"\b")}


def _cue_pattern(cue: str) -> str:
    return cue if cue in _REGEX_CUES else rf"\b{re.escape(cue)}\b"

# Movement direction comes from the word in front of each place, not from which
# place is mentioned first: in "back to the tavern after leaving Greyspine
# Manor" the trip runs Manor -> tavern although the tavern comes first.
ORIGIN_MARKERS = [
    "from", "leaving", "left", "out of", "departing", "departed",
    "exiting", "exited", "fleeing", "fled", "escaping", "escaped",
]
DESTINATION_MARKERS = [
    "to", "toward", "towards", "into", "onto", "reached", "reaching",
    "arrived at", "arrived in", "arrive at", "arrive in", "arriving at",
    "arriving in", "entered", "entering",
]

# A compass answer from the model must be anchored in the sentence; without
# one it invented "tavern west_of Greyspine Manor" for a plain journey.
COMPASS_WORD = re.compile(r"\b(?:north|south|east|west)", re.IGNORECASE)
COMPASS_RELATIONS = {
    SpatialRelation.north_of, SpatialRelation.south_of,
    SpatialRelation.east_of, SpatialRelation.west_of,
}

NO_RELATION = "NONE"

# A relation the model may recognise but that has no place on a map: "behind",
# "above" and the like depend on where the viewer stands, not on where the
# places are. It is offered as an answer so the model has somewhere to put
# them instead of forcing a compass direction, but it never becomes an edge,
# which is why it is a plain string and not a SpatialRelation member.
NON_MAP_RELATION = "other"

# What the reverse question must answer for a directional relation to be kept.
INVERSE: dict[SpatialRelation, SpatialRelation] = {
    SpatialRelation.north_of: SpatialRelation.south_of,
    SpatialRelation.south_of: SpatialRelation.north_of,
    SpatialRelation.east_of: SpatialRelation.west_of,
    SpatialRelation.west_of: SpatialRelation.east_of,
    SpatialRelation.inside: SpatialRelation.contains,
    SpatialRelation.contains: SpatialRelation.inside,
}

VALIDATOR_ANSWERS = (
    [relation.value for relation in SpatialRelation]
    + [NON_MAP_RELATION, NO_RELATION]
)

# Kept verbatim from the evaluation run; rewording it invalidates the results
# quoted in the module docstring.
VALIDATOR_PROMPT = (
    "You decide whether a text states a spatial relation between two named "
    "places on a map.\n"
    "Answer with exactly one value from this list and nothing else:\n"
    + ", ".join(VALIDATOR_ANSWERS)
    + "\n\n"
    "Rules:\n"
    "- Answer NONE unless the text clearly states how place A relates to place B.\n"
    "- Answer NONE if either place is really a person, creature, object or time "
    "expression.\n"
    "- Answer NONE if the relation is to a pronoun (you, it, them) and not to "
    "place B.\n"
    "- Answer NONE for time expressions such as 'the near future' or 'within "
    "the time'.\n"
    "- Relations like 'behind', 'in front of', 'above', 'below' depend on the "
    "viewer, not the map: answer other for those.\n"
    "- Only answer travelled_to if someone actually moves from A to B."
)


def _place_spans(sentence: str, places: list[str]) -> list[tuple[int, int, str]]:
    lowered = sentence.casefold()
    spans: list[tuple[int, int, str]] = []

    for place in set(places):
        for match in re.finditer(rf"\b{re.escape(place.casefold())}\b", lowered):
            spans.append((match.start(), match.end(), place))

    spans.sort()

    # Drop a span fully contained in a longer one ("castle" inside "Castle Ravenwatch").
    return [
        span for span in spans
        if not any(
            other is not span and other[0] <= span[0] and span[1] <= other[1]
            for other in spans
        )
    ]


def extract_cue_relations(
    sentence: str,
    places: list[str],
    allow_travel: bool = False,
) -> list[tuple[str, SpatialRelation, str]]:
    """Tier 1: deterministic cue + word order. Returns [] when nothing matches."""

    spans = _place_spans(sentence, places)

    if len({span[2] for span in spans}) < 2:
        return []

    lowered = sentence.casefold()

    for cue, relation in CUES:
        for match in re.finditer(_cue_pattern(cue), lowered):
            if cue == "in" and NOT_CONTAINMENT_AFTER_IN.match(lowered[match.end():]):
                continue

            if _negated(lowered, match.start()):
                continue

            before = [
                span for span in spans
                if span[1] <= match.start()
                and match.start() - span[1] <= MAX_CUE_GAP
                and not CLAUSE_BREAK.search(lowered[span[1]:match.start()])
            ]
            after = [
                span for span in spans
                if span[0] >= match.end()
                and span[0] - match.end() <= MAX_CUE_GAP
                and not CLAUSE_BREAK.search(lowered[match.end():span[0]])
            ]

            if not before or not after or before[-1][2] == after[0][2]:
                continue

            if cue == "of":
                tail = re.split(r"[\s\-]+", before[-1][2].casefold())[-1]
                if tail not in PART_WORDS:
                    continue

            return [(before[-1][2], relation, after[0][2])]

    if not allow_travel:
        return []

    origins = _marked_places(lowered, spans, ORIGIN_MARKERS)
    destinations = _marked_places(lowered, spans, DESTINATION_MARKERS)

    for origin in origins:
        for destination in reversed(destinations):
            if destination != origin:
                return [(origin, SpatialRelation.travelled_to, destination)]

    return []


def _marked_places(
    lowered: str,
    spans: list[tuple[int, int, str]],
    markers: list[str],
) -> list[str]:
    """Places, in text order, that directly follow one of ``markers``."""

    marked: dict[int, str] = {}

    for marker in markers:
        for match in re.finditer(rf"\b{re.escape(marker)}\b", lowered):
            if _negated(lowered, match.start()):
                continue

            following = [
                span for span in spans
                if span[0] >= match.end() and span[0] - match.end() <= MAX_CUE_GAP
            ]
            if following:
                marked[following[0][0]] = following[0][2]

    return [marked[position] for position in sorted(marked)]


def adjacent_pairs(sentence: str, places: list[str]) -> list[tuple[str, str]]:
    """Neighbouring places in text order: n places give at most n - 1 pairs."""

    ordered: list[str] = []

    for _, _, place in _place_spans(sentence, places):
        if not ordered or ordered[-1] != place:
            ordered.append(place)

    return [(a, b) for a, b in zip(ordered, ordered[1:]) if a != b]


def parse_validator_answer(answer: object) -> str:
    """Snap a model reply onto the closed answer set; anything else is NONE."""

    text = str(answer or "").strip().casefold()

    # The value the reply leads with is the answer: "NONE (not inside)" is NONE.
    positions = [
        (match.start(), value)
        for value in VALIDATOR_ANSWERS
        if (match := re.search(rf"\b{re.escape(value.casefold())}\b", text))
    ]

    return min(positions)[1] if positions else NO_RELATION


def _ollama_pair_relation(text: str, place_a: str, place_b: str) -> str:
    # Imported here so the module stays importable without the settings stack.
    model = MAP_AI_MODEL
    if not model:
        from app.core.config import settings

        model = settings.llm_model

    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 12},
        "messages": [
            {"role": "system", "content": VALIDATOR_PROMPT},
            {
                "role": "user",
                "content": (
                    f'Text: "{text}"\nPlace A: {place_a}\n'
                    f"Place B: {place_b}\nAnswer:"
                ),
            },
        ],
    }

    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=MAP_AI_TIMEOUT) as response:
        return json.loads(response.read())["message"]["content"]


def extract_relations(
    sentences: dict[int, tuple[str, list[str]]],
    llm=None,
    travel: set[int] | None = None,
) -> dict[int, list[tuple[str, SpatialRelation, str]]]:
    """
    Run both tiers over {index: (sentence, places)}.

    ``travel`` holds the indices whose sentence comes from a travel event; only
    those may use the movement patterns. ``llm`` is the tier-2 seam, called as
    ``llm(text, place_a, place_b)`` and expected to return one of
    VALIDATOR_ANSWERS. Pass a fake in tests; with no model only tier 1 runs.
    """

    travel = travel or set()
    results: dict[int, list[tuple[str, SpatialRelation, str]]] = {}
    pending: list[tuple[int, str, str, str]] = []

    for index, (sentence, places) in sentences.items():
        cue_hits = extract_cue_relations(
            sentence, places, allow_travel=index in travel
        )

        if cue_hits:
            results[index] = cue_hits
            continue

        for place_a, place_b in adjacent_pairs(sentence, places):
            pending.append((index, sentence, place_a, place_b))

    if not pending:
        return results

    if llm is None and MAP_AI_ENABLED:
        llm = _ollama_pair_relation

    if llm is None:
        return results

    if len(pending) > MAP_AI_MAX_PAIRS:
        print(
            f"Map relation validator: {len(pending)} pairs, "
            f"checking the first {MAP_AI_MAX_PAIRS}."
        )
        pending = pending[:MAP_AI_MAX_PAIRS]

    for index, sentence, place_a, place_b in pending:
        try:
            triple = _validated_relation(
                llm, sentence, place_a, place_b, travel=index in travel
            )
        except Exception as error:  # noqa: BLE001 - degrade, never crash
            # One failure means no model server; stop instead of timing out
            # on every remaining pair.
            print(f"Map relation validator unavailable: {error}")
            break

        if triple is not None:
            results.setdefault(index, []).append(triple)

    return results


def _validated_relation(
    llm,
    sentence: str,
    place_a: str,
    place_b: str,
    travel: bool = False,
) -> tuple[str, SpatialRelation, str] | None:
    """Ask about A -> B; confirm directional answers by asking B -> A."""

    travelled = SpatialRelation.travelled_to.value
    answer = parse_validator_answer(llm(sentence, place_a, place_b))

    # A compass direction the sentence never mentions is no answer at all.
    compass = {relation.value for relation in COMPASS_RELATIONS}
    if answer in compass and not COMPASS_WORD.search(sentence):
        answer = NO_RELATION

    if answer == NO_RELATION:
        # Pairs are asked in text order, but movement often runs the other way
        # ("back to the tavern after leaving Greyspine Manor"). In a travel
        # event, give the reverse direction one chance.
        if travel and parse_validator_answer(llm(sentence, place_b, place_a)) == travelled:
            return place_b, SpatialRelation.travelled_to, place_a
        return None

    if answer == NON_MAP_RELATION:
        return None

    relation = SpatialRelation(answer)

    if relation in INVERSE:
        reverse = parse_validator_answer(llm(sentence, place_b, place_a))
        return (place_a, relation, place_b) if reverse == INVERSE[relation].value else None

    if relation == SpatialRelation.travelled_to:
        # Movement both ways in one sentence means the model ignored the order.
        if parse_validator_answer(llm(sentence, place_b, place_a)) == travelled:
            return None

    return place_a, relation, place_b
