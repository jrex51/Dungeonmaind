"""Turn timeline events into the inputs the map needs (Release 3).

The timeline already decides which strings are places and when they occur, so
the map does not detect locations itself. It uses the timeline as an index:
for every event, take the transcript segments around the event's timestamps
(plus one neighbouring segment each side, because a place is often described
just before or after the action), and keep the sentences that mention at least
two of that event's known locations. Relation extraction then only has to
decide how those places relate.

Imports of the timeline store and the embedding layer are deferred to the
loader functions: both pull in heavy dependencies (settings, ChromaDB) that the
rest of this module - and its tests - do not need.
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable


MIN_SENTENCE_LENGTH = 15

# Transcript segments taken either side of an event's own span.
NEIGHBOUR_SEGMENTS = 1


@dataclass(frozen=True)
class Segment:
    text: str
    start: float
    end: float


@dataclass
class Candidate:
    """A transcript sentence mentioning two or more known places."""

    text: str
    places: list[str]
    timestamp: float
    travel: bool = False
    event_ids: list[str] = field(default_factory=list)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_timeline_events() -> list:
    from app.functions.timeline.timeline_store import timeline_store

    return timeline_store.list_events()


def load_transcript_documents() -> list:
    from app.functions.embedding.embedding_model import (
        get_all_transcription_documents,
    )

    return get_all_transcription_documents()


def segments_from_documents(documents: Iterable) -> list[Segment]:
    """Transcript documents as time-ordered segments."""

    segments: list[Segment] = []

    for document in documents:
        text = (getattr(document, "page_content", "") or "").strip()
        if not text:
            continue

        metadata = getattr(document, "metadata", None) or {}
        start = max(0.0, _safe_float(metadata.get("start_time")))
        end = max(start, _safe_float(metadata.get("end_time"), start))
        segments.append(Segment(text=text, start=start, end=end))

    segments.sort(key=lambda segment: (segment.start, segment.end))
    return segments


def split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if len(sentence.strip()) >= MIN_SENTENCE_LENGTH
    ]


def mentioned_places(text: str, places: Iterable[str]) -> list[str]:
    """Known places that occur in ``text`` as whole words, in text order."""

    lowered = text.casefold()
    found: list[tuple[int, str]] = []

    for place in dict.fromkeys(p.strip() for p in places if p and p.strip()):
        match = re.search(rf"\b{re.escape(place.casefold())}\b", lowered)
        if match:
            found.append((match.start(), place))

    return [place for _, place in sorted(found)]


def is_travel_event(event) -> bool:
    # TimelineCategory is a str enum, so this also accepts plain strings.
    return getattr(event, "category", None) == "travel"


def event_window(
    segments: list[Segment],
    start: float,
    end: float,
    neighbours: int = NEIGHBOUR_SEGMENTS,
) -> list[int]:
    """Indices of the segments overlapping [start, end], widened by ``neighbours``."""

    overlapping = [
        index
        for index, segment in enumerate(segments)
        if segment.start <= end and segment.end >= start
    ]

    if not overlapping:
        return []

    low = max(0, overlapping[0] - neighbours)
    high = min(len(segments) - 1, overlapping[-1] + neighbours)
    return list(range(low, high + 1))


def collect_candidates(
    events: Iterable,
    segments: list[Segment],
    canonical: Callable[[str], str] = lambda name: name,
) -> list[Candidate]:
    """
    Sentences, around each event, that mention two or more distinct places.

    Windows of neighbouring events overlap, so a sentence is kept once and the
    places and travel flags of every event that reached it are merged. When no
    transcript segment overlaps an event (the transcript was cleared, say), the
    event's own source segments are used instead.
    """

    merged: dict[tuple, Candidate] = {}

    for event in events:
        places = list(getattr(event, "locations", None) or [])
        if len({canonical(place) for place in places}) < 2:
            continue

        is_travel = is_travel_event(event)
        window = event_window(segments, event.start_time, event.end_time)

        if window:
            sources = [(("t", index), segments[index]) for index in window]
        else:
            sources = [
                (("e", event.id, position), Segment(s.text, s.start_time, s.end_time))
                for position, s in enumerate(getattr(event, "source_segments", []) or [])
            ]

        for source_key, segment in sources:
            for position, sentence in enumerate(split_sentences(segment.text)):
                found = mentioned_places(sentence, places)
                if len({canonical(place) for place in found}) < 2:
                    continue

                key = (*source_key, position)
                candidate = merged.get(key)

                if candidate is None:
                    merged[key] = Candidate(
                        text=sentence,
                        places=found,
                        timestamp=segment.start,
                        travel=is_travel,
                        event_ids=[event.id],
                    )
                else:
                    candidate.places = mentioned_places(
                        sentence, [*candidate.places, *found]
                    )
                    candidate.travel = candidate.travel or is_travel
                    candidate.event_ids.append(event.id)

    return sorted(merged.values(), key=lambda candidate: candidate.timestamp)
