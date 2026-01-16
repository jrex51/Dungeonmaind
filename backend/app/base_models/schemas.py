from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Use the domain enums as the single source of truth
from app.domain.models import Role, PlayerStatus


# Input models
class PlayerIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    role: Role
    reuse_id: Optional[UUID] = None  # used for re-join / reuse flow


# Abilities
class Abilities(BaseModel):
    # "int_" kept to match frontend & domain model
    str: int
    dex: int
    con: int
    int_: int
    wis: int
    cha: int


class AbilitiesIn(BaseModel):
    str: Optional[int] = None
    dex: Optional[int] = None
    con: Optional[int] = None
    int_: Optional[int] = None
    wis: Optional[int] = None
    cha: Optional[int] = None


# HP (nested)
class Hp(BaseModel):
    current: int = 0
    max: int = 10
    temp: int = 0


class HpPatch(BaseModel):
    current: Optional[int] = Field(None, ge=0)
    max: Optional[int] = Field(None, ge=1)
    temp: Optional[int] = Field(None, ge=0)


class MaxHpUpdate(BaseModel):
    max: int = Field(..., ge=1)


# Output models
class PlayerOut(BaseModel):
    id: UUID
    name: str
    role: Role
    status: PlayerStatus
    hp: Hp = Field(default_factory=Hp)
    created_at: datetime
    last_seen_at: datetime
    abilities: Optional[Abilities] = None
    backend_url: Optional[str] = None
    has_voiceprint: bool = False


# Optional: unified patch model (not currently used by routes)
class PlayerPatch(BaseModel):
    name: Optional[str] = None
    role: Optional[Role] = None

    hp: Optional[HpPatch] = None
    abilities: Optional[AbilitiesIn] = None

    # flat ability fields
    str: Optional[int] = None
    dex: Optional[int] = None
    con: Optional[int] = None
    int_: Optional[int] = None
    wis: Optional[int] = None
    cha: Optional[int] = None


# Action bodies
class PlayerDamageBody(BaseModel):
    damage: int = Field(..., ge=0)


class PlayerHealBody(BaseModel):
    heal: int = Field(..., ge=0)


# Group state
class GroupStateOut(BaseModel):
    group_id: UUID
    size: int
    max_size: int


# For /players/join/check
class JoinCheckOut(BaseModel):
    status: Literal["available", "inactive_match", "active_conflict"]
    candidate: Optional[PlayerOut] = None
