import asyncio

from fastapi import APIRouter

from app.base_models.timeline_models import (
    TimelineEventCreate,
    TimelineGenerationResponse,
    TimelineResponse,
)
from app.functions.timeline.timeline_generator import (
    generate_timeline_from_embeddings,
)
from app.functions.timeline.timeline_store import timeline_store
from app.functions.geographic_mapping.session_integration import get_lifecycle, get_map_store


router = APIRouter()


@router.get(
    "/events",
    response_model=TimelineResponse,
    summary="Return the stored timeline",
)
async def list_timeline_events() -> TimelineResponse:
    """Read existing timeline events without running generation."""
    events = await asyncio.to_thread(timeline_store.list_events)

    return TimelineResponse(
        events=events,
        total=len(events),
    )


def _generate_and_store_timeline() -> TimelineGenerationResponse:
    events, source_segment_count = generate_timeline_from_embeddings()
    TimelineGenerationResponse(
        events=events, generated_count=len(events), source_segment_count=source_segment_count,
    )
    # Validate the entire result before invalidating either generated view.
    event_data = [TimelineEventCreate.model_validate(event.model_dump()) for event in events]
    map_store = get_map_store()
    previous_map = map_store.get_map()
    previous_events = timeline_store.snapshot()
    # Clear before committing so readers cannot see the old map with a new
    # timeline. If an atomic save fails without changing the timeline, restore
    # its still-valid map. A partially changed timeline must retain no old map.
    map_store.clear_map()
    # The store assigns IDs and timestamps; retain all generated event content.
    try:
        stored_events = timeline_store.replace_events(event_data)
    except Exception:
        if timeline_store.snapshot() == previous_events:
            map_store.replace_map(previous_map)
        raise
    return TimelineGenerationResponse(
        events=stored_events,
        generated_count=len(stored_events),
        source_segment_count=source_segment_count,
    )


@router.post(
    "/generate",
    response_model=TimelineGenerationResponse,
    summary="Generate timeline from transcription embeddings",
)
async def generate_timeline() -> TimelineGenerationResponse:
    """
    Read all transcription documents from ChromaDB, arrange them by
    timestamp, group nearby segments and generate timeline events.

    Replace the stored timeline only after generation succeeds.
    """

    return await get_lifecycle().run(
        lambda: asyncio.to_thread(_generate_and_store_timeline)
    )
