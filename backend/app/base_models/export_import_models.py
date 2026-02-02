from pydantic import BaseModel, Field
from typing import List, Dict
from app.domain.models import Role
from app.base_models.schemas import PlayerOut
from uuid import UUID
from datetime import datetime
from enum import Enum


class ExportRequest(BaseModel):
    campaign_name: str = Field(..., description="Name of the campaign where the session has to be saved")
    session_name: str = Field(..., description="Name of the session to be saved")


class ImportRequest(BaseModel):
    campaign_name: str = Field(..., description="Name of the campaign where the session has to be saved")
    session_name: str = Field(..., description="Name of the session to be loaded")


class RenameRequest(BaseModel):
    campaign_name: str = Field(..., description="Name of the campaign where the session is saved")
    old_session_name: str = Field(..., description="Name of the saved session")
    new_session_name: str = Field(..., description="New name of the saved session")


class DeleteRequest(BaseModel):
    campaign_or_session_name: str = Field(..., description="Name of the campaign or session to be deleted")


class Sessions(BaseModel):
    folders: List[str]


class Campaigns(BaseModel):
    campaigns: Dict[str, Sessions]


# If needed later
class GroupOut(BaseModel):
    id: UUID
    max_size: int
    players: list[PlayerOut]
