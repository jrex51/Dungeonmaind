import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from app.functions.timeline.timeline_models import TimelineEvent


_timeline_events: list[TimelineEvent] = []
_timeline_lock = asyncio.Lock()


def _is_valid_segment_text(text: str) -> bool:
    cleaned_text = text.strip()
    if len(cleaned_text) < 5:
        return False

    if cleaned_text.isnumeric():
        return False

    return any(character.isalpha() for character in cleaned_text)


def extract_timeline_events(segments: Sequence[Mapping[str, Any]]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    seen_events: set[tuple[float, str, str]] = set()

    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not _is_valid_segment_text(text):
            continue

        timestamp = float(segment.get("start", 0.0))
        event = TimelineEvent(
            timestamp=timestamp,
            title=text[:40],
            description=text,
        )
        signature = (event.timestamp, event.title, event.description)
        if signature in seen_events:
            continue

        seen_events.add(signature)
        events.append(event)

    return events


async def append_timeline_events(segments: Sequence[Mapping[str, Any]]) -> list[TimelineEvent]:
    events = extract_timeline_events(segments)
    if not events:
        return await get_timeline_events()

    async with _timeline_lock:
        existing_signatures = {
            (event.timestamp, event.title, event.description)
            for event in _timeline_events
        }

        new_events = []
        for event in events:
            signature = (event.timestamp, event.title, event.description)
            if signature in existing_signatures:
                continue

            existing_signatures.add(signature)
            new_events.append(event)

        _timeline_events.extend(new_events)
        _timeline_events.sort(key=lambda event: event.timestamp)
        return list(_timeline_events)


async def get_timeline_events() -> list[TimelineEvent]:
    async with _timeline_lock:
        return list(_timeline_events)


async def clear_timeline_events() -> None:
    async with _timeline_lock:
        _timeline_events.clear()