from fastapi import APIRouter

from app.functions.timeline.timeline_extractor import get_timeline_events
from app.functions.timeline.timeline_models import TimelineEvent

router = APIRouter()


@router.get("", response_model=list[TimelineEvent])
async def read_timeline() -> list[TimelineEvent]:
    return await get_timeline_events()