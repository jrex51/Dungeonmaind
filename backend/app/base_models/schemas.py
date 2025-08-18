from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field


class Role(str, Enum):
    leader = "leader"
    member = "member"

class PlayerIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    role: Role

class PlayerOut(BaseModel):
    id: UUID
    name: str
    role: Role
    created_at: datetime
    last_seen_at: datetime

class GroupStateOut(BaseModel):
    group_id: UUID
    size: int
    max_size: int