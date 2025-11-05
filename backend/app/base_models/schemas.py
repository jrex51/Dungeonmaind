from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Literal
from uuid import UUID
from pydantic import BaseModel, Field


class Role(str, Enum):
    leader = "leader"
    member = "member"

class PlayerIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    role: Role
    reuse_id: Optional[UUID] = None

class PlayerOut(BaseModel):
    id: UUID
    name: str
    role: Role
    max_hp: int = 10
    hp: int = 0
    temp_hp: int = 0
    created_at: datetime
    last_seen_at: datetime

class PlayerHealthPatch(BaseModel):
    hp: Optional[int] = Field(None, ge=0)
    max_hp: Optional[int] = Field(None, ge=1)
    temp_hp: Optional[int] = Field(None, ge=0)

class PlayerDamageBody(BaseModel):
    damage: int = Field(..., ge=0)

class PlayerHealBody(BaseModel):
    heal: int = Field(..., ge=0)

class PlayerAttributesPatch(BaseModel):
    attributes: Dict[str, str]

class GroupStateOut(BaseModel):
    group_id: UUID
    size: int
    max_size: int

class PlayerJoinIn(BaseModel):
    name: str
    role: Role
    reuse_id: Optional[UUID] = None

class JoinCheckOut(BaseModel):
    status: Literal["available", "inactive_match", "active_conflict"]
    candidate: Optional[PlayerOut] = None
