import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from app.functions.timeline.timeline_models import TimelineEvent


_timeline_events: list[TimelineEvent] = []
_timeline_lock = asyncio.Lock()


def extract_timeline_events(segments: Sequence[Mapping[str, Any]]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []

    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        timestamp = float(segment.get("start", 0.0))
        events.append(
            TimelineEvent(
                timestamp=timestamp,
                title=text[:40],
                description=text,
            )
        )

    return events


async def append_timeline_events(segments: Sequence[Mapping[str, Any]]) -> list[TimelineEvent]:
    events = extract_timeline_events(segments)
    if not events:
        return await get_timeline_events()

    async with _timeline_lock:
        _timeline_events.extend(events)
        _timeline_events.sort(key=lambda event: event.timestamp)
        return list(_timeline_events)


async def get_timeline_events() -> list[TimelineEvent]:
    async with _timeline_lock:
        return list(_timeline_events)


async def clear_timeline_events() -> None:
    async with _timeline_lock:
        _timeline_events.clear()