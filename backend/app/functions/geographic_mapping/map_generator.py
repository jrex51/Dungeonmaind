"""Build the campaign map from the timeline (Release 3, issue #48).

Pipeline:

    timeline events (locations, timestamps, category)
        -> canonical place names          (alias map)
        -> nodes
        -> transcript sentences around each event that mention 2+ of its places
                                          (map_sources)
        -> stated relations               (spatial_relation_extractor)
        -> journey edges                  (travel events in time order)
        -> MapData

The timeline has already decided what is a place - with exact-span checks and
filters for speaker names, time phrases and non-places - so nothing here
detects locations. Journey edges carry most of the map: real sessions describe
where the party goes far more often than how places sit relative to each other.
"""

import re
from datetime import datetime, timezone
from itertools import chain
from typing import Iterable

from app.base_models.map_models import (
    LocationKind,
    MapData,
    MapEdge,
    MapNode,
    SpatialRelation,
    make_edge_id,
    make_node_id,
)
from app.functions.geographic_mapping.map_sources import (
    collect_candidates,
    is_travel_event,
    load_timeline_events,
    load_transcript_documents,
    segments_from_documents,
)
from app.functions.geographic_mapping.spatial_relation_extractor import (
    INVERSE,
    extract_relations,
    travel_endpoints,
)
from app.functions.timeline.timeline_ai import transcript_sentences


DETERMINERS = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)

# Relations that describe where places are, as opposed to movement between them.
STATIC_RELATIONS = set(INVERSE) | {
    SpatialRelation.near,
    SpatialRelation.connected_to,
}


def _generic_location_words() -> set[str]:
    # The timeline module imports sentence-transformers at load time, so it is
    # only imported when a real generation runs, never by tests of this module.
    from app.functions.timeline.timeline_generator import GENERIC_LOCATION_WORDS

    return set(GENERIC_LOCATION_WORDS)


def location_kind(name: str, generic_words: set[str]) -> LocationKind:
    """
    Named if any word after the article is capitalised ("the Greyspine Mines"),
    generic otherwise - and always generic when the whole name is a generic
    place word, so a sentence-initial "Tavern" is not taken for a proper name.
    """

    core = DETERMINERS.sub("", name.strip())

    if core.casefold() in generic_words:
        return LocationKind.generic

    if any(word[:1].isupper() for word in core.split()):
        return LocationKind.named

    return LocationKind.generic


def build_alias_map(
    names: Iterable[str],
    generic_words: set[str],
    transcript_texts: Iterable[str] = (),
) -> dict[str, str]:
    """
    Map surface forms onto a canonical place name.

    A generic form is absorbed into a named one that contains it, so "the
    castle" merges into "Castle Ravenwatch" instead of becoming its own node.
    Deterministic on purpose: asking a model to cluster names produced
    containment errors ("the central ring" merged into "Kraghammer").
    """

    unique = {name.strip() for name in names if name and name.strip()}

    named = sorted(
        (n for n in unique if location_kind(n, generic_words) == LocationKind.named),
        key=lambda name: (-len(name), name),
    )

    alias_of: dict[str, str] = {}
    spaced: dict[str, list[str]] = {}
    for name in named:
        words = name.split()
        if len(words) > 1 and all(word.isalpha() and word[0].isupper() for word in words):
            spaced.setdefault("".join(words).casefold(), []).append(name)

    # ASR can write a proper name as one word. Use only spellings present in
    # the source, and only when they match a single established multiword name.
    joined = {key: names[0] for key, names in spaced.items() if len(names) == 1}
    alias_of.update(
        {name: joined[name.casefold()] for name in unique if name.casefold() in joined}
    )
    if joined:
        pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, joined)) + r")\b", re.IGNORECASE)
        for text in transcript_texts:
            for match in pattern.finditer(text):
                spelling = match.group()
                if spelling[0].isupper():
                    alias_of[spelling] = joined[spelling.casefold()]

    for candidate in unique:
        if candidate in named or candidate in alias_of:
            continue

        core = DETERMINERS.sub("", candidate).casefold()

        for full in named:
            if re.search(rf"\b{re.escape(core)}\b", full.casefold()):
                alias_of[candidate] = full
                break

    return alias_of


def _event_text(event) -> str:
    segments = getattr(event, "source_segments", None) or []
    return " ".join(segment.text for segment in segments) or event.description


def _same_spot(a: str, b: str) -> bool:
    """True when one name sits inside the other as whole words."""

    shorter, longer = sorted((a, b), key=len)
    return bool(re.search(rf"\b{re.escape(shorter)}\b", longer))


def _fact_key(source: str, relation: SpatialRelation, target: str) -> tuple:
    """
    One key per fact however it was phrased: "A north_of B" and "B south_of A"
    are the same fact, as are "A near B" and "B near A". Movement keeps its
    direction. Used only for merging - edges keep their first phrasing.
    """

    if relation in STATIC_RELATIONS and source > target:
        return target, INVERSE.get(relation, relation), source

    return source, relation, target


def generate_map(
    events: list | None = None,
    documents: list | None = None,
    relation_llm=None,
    generic_words: set[str] | None = None,
) -> MapData:
    """
    Build the map from the stored timeline and transcript.

    Every argument is a seam: tests pass events, transcript documents, a fake
    relation validator and the generic-word set so the pipeline runs offline.
    """

    if events is None:
        events = load_timeline_events()

    generated_at = datetime.now(timezone.utc).isoformat()
    located = [event for event in events if getattr(event, "locations", None)]

    if not located:
        return MapData(source_segment_count=len(events), generated_at=generated_at)

    if documents is None:
        documents = load_transcript_documents()

    if generic_words is None:
        generic_words = _generic_location_words()

    segments = segments_from_documents(documents)
    alias_of = build_alias_map(
        (place for event in located for place in event.locations),
        generic_words,
        chain(
            (segment.text for segment in segments),
            (
                source.text
                for event in located
                for source in getattr(event, "source_segments", None) or []
            ),
        ),
    )

    def canonical(name: str) -> str:
        return alias_of.get(name.strip(), name.strip())

    # ---- nodes -------------------------------------------------------
    nodes: dict[str, MapNode] = {}
    aliases: dict[str, list[str]] = {}
    for spelling, name in sorted(alias_of.items()):
        aliases.setdefault(name, []).append(spelling)

    for event in sorted(located, key=lambda e: e.start_time):
        for name in dict.fromkeys(canonical(raw) for raw in event.locations):
            node_id = make_node_id(name)
            node = nodes.get(node_id)

            if node is None:
                nodes[node_id] = MapNode(
                    id=node_id,
                    name=name,
                    kind=location_kind(name, generic_words),
                    first_seen=event.start_time,
                    last_seen=max(event.start_time, event.end_time),
                )
            else:
                node.mentions += 1
                node.last_seen = max(node.last_seen, event.end_time)

    for node in nodes.values():
        node.aliases = aliases.get(node.name, [])

    # ---- edges: stated relations ---------------------------------------
    candidates = collect_candidates(located, segments, canonical, aliases)

    found = extract_relations(
        {index: (c.text, c.places) for index, c in enumerate(candidates)},
        llm=relation_llm,
        travel={index for index, c in enumerate(candidates) if c.travel},
    )

    facts: dict[tuple, MapEdge] = {}

    for index, relations in sorted(found.items()):
        candidate = candidates[index]

        for source_name, relation, target_name in relations:
            source_id = make_node_id(canonical(source_name))
            target_id = make_node_id(canonical(target_name))

            if source_id == target_id or {source_id, target_id} - nodes.keys():
                continue

            key = _fact_key(source_id, relation, target_id)

            if key in facts:
                facts[key].count += 1
                continue

            facts[key] = MapEdge(
                id=make_edge_id(source_id, relation, target_id),
                source=source_id,
                target=target_id,
                relation=relation,
                evidence=candidate.text[:2000],
                timestamp=candidate.timestamp,
            )

    # Conflicting descriptions of one pair (north_of here, inside there): keep
    # the most repeated, then the earliest.
    by_pair: dict[frozenset, list[MapEdge]] = {}
    for edge in facts.values():
        if edge.relation in STATIC_RELATIONS:
            by_pair.setdefault(frozenset((edge.source, edge.target)), []).append(edge)

    dropped = {
        edge.id
        for group in by_pair.values() if len(group) > 1
        for edge in group
        if edge is not max(group, key=lambda e: (e.count, -e.timestamp))
    }

    edges: dict[str, MapEdge] = {
        edge.id: edge for edge in facts.values() if edge.id not in dropped
    }

    # ---- edges: the journey ---------------------------------------------
    stated_travel = {
        (edge.source, edge.target)
        for edge in edges.values()
        if edge.relation == SpatialRelation.travelled_to
    }
    confirmed: set[str] = set()
    journey: list[tuple[str, bool, str, float]] = []

    for event in sorted(located, key=lambda e: e.start_time):
        if not is_travel_event(event):
            continue

        event_names = list(dict.fromkeys(canonical(place) for place in event.locations))
        places = list(event_names)
        for name in event_names:
            places.extend(aliases.get(name, []))
        endpoints: list[tuple[str, bool, str]] = []
        for sentence in transcript_sentences(_event_text(event)):
            for origins, destinations in travel_endpoints(sentence, places):
                endpoints.extend((canonical(place), False, sentence) for place in origins)
                endpoints.extend((canonical(place), True, sentence) for place in destinations)

        # Within one event, a name inside another name is the same spot, not a
        # second stop: the timeline once listed both "Waterdeep" and the
        # transcription slip "Waterdeep Adorn" for one sentence, which drew a
        # trip from Waterdeep to itself.
        names = {name.casefold() for name, _, _ in endpoints}
        stops: set[str] = set()
        for name, destination, sentence in endpoints:
            node_id = make_node_id(name)
            if node_id in stops or any(
                len(other) < len(name) and _same_spot(name.casefold(), other) for other in names
            ):
                continue
            stops.add(node_id)
            if node_id in nodes and (not journey or journey[-1][0] != node_id):
                journey.append((node_id, destination, sentence, event.start_time))

    for (source_id, *_), (target_id, destination, sentence, timestamp) in zip(journey, journey[1:]):
        if not destination or source_id == target_id:
            continue

        # Text order is not always travel order ("reached Neverwinter, having
        # left Waterdeep"); a stated movement the other way wins.
        if (target_id, source_id) in stated_travel and (source_id, target_id) not in stated_travel:
            continue

        edge_id = make_edge_id(source_id, SpatialRelation.travelled_to, target_id)
        existing = edges.get(edge_id)

        if existing is None:
            edges[edge_id] = MapEdge(
                id=edge_id,
                source=source_id,
                target=target_id,
                relation=SpatialRelation.travelled_to,
                evidence=sentence[:2000],
                timestamp=timestamp,
            )
            confirmed.add(edge_id)
        elif edge_id not in confirmed:
            # First journey sighting of a stated movement is the same trip.
            confirmed.add(edge_id)
        else:
            existing.count += 1

    return MapData(
        nodes=sorted(nodes.values(), key=lambda node: (-node.mentions, node.name)),
        edges=sorted(edges.values(), key=lambda edge: edge.timestamp),
        source_segment_count=len(events),
        generated_at=generated_at,
    )
