from pydantic import BaseModel, Field
from typing import List
from app.domain.models import Role
from app.base_models.schemas import PlayerOut
from uuid import UUID
from datetime import datetime
from enum import Enum


class ExportRequest(BaseModel):
    session_name: str = Field(..., description="Name of the session to be saved")


class ImportRequest(BaseModel):
    session_name: str = Field(..., description="Name of the session to be loaded")


class Sessions(BaseModel):
    folders: List[str]


# If needed later
class GroupOut(BaseModel):
    id: UUID
    max_size: int
    players: list[PlayerOut]
