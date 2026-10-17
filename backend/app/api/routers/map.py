"""Read the stored map or explicitly regenerate it from the timeline."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.base_models.map_models import MapData
from app.functions.geographic_mapping.map_generator import generate_map
from app.functions.geographic_mapping.map_store import MapStore
from app.functions.geographic_mapping.session_integration import get_lifecycle, get_map_store


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=MapData, summary="Retrieve the stored geographic map")
async def get_map(store: MapStore = Depends(get_map_store)) -> MapData:
    try:
        return await asyncio.to_thread(store.get_map)
    except Exception as error:
        logger.exception("Unable to read geographic map")
        raise HTTPException(
            status_code=500, detail="Unable to read the stored map"
        ) from error


def _generate_and_store(store: MapStore) -> MapData:
    return store.replace_map(generate_map())


@router.post("/generate", response_model=MapData, summary="Generate and store a geographic map")
async def regenerate_map(store: MapStore = Depends(get_map_store)) -> MapData:
    try:
        return await get_lifecycle().run(
            lambda: asyncio.to_thread(_generate_and_store, store)
        )
    except Exception as error:
        logger.exception("Unable to generate geographic map")
        raise HTTPException(
            status_code=500, detail="Map generation failed; previous map retained"
        ) from error
