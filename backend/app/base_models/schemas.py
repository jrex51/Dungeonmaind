from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---- Core enums ----
class Role(str, Enum):
    leader = "leader"
    member = "member"


# ---- Input models ----
class PlayerIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    role: Role


# ---- Abilities ----
class Abilities(BaseModel):
    # Keep "int_" to match the frontend keys exactly
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


# ---- HP (nested) ----
class Hp(BaseModel):
    current: int = 0
    max: int = 10
    temp: int = 0


class HpPatch(BaseModel):
    current: Optional[int] = Field(None, ge=0)
    max: Optional[int] = Field(None, ge=1)
    temp: Optional[int] = Field(None, ge=0)


# ---- Output models ----
class PlayerOut(BaseModel):
    id: UUID
    name: str
    role: Role
    hp: Hp = Field(default_factory=Hp)
    created_at: datetime
    last_seen_at: datetime
    abilities: Optional[Abilities] = None
    backend_url: Optional[str] = None


# ---- Patch models ----
class PlayerPatch(BaseModel):
    """
    Unified player patch payload.

    Supports:
      - Nested HP patch:   { "hp": { "current": 7 } }
      - Nested abilities:  { "abilities": { "str": 12 } }
      - (Optional) flat ability keys for convenience:
                           { "str": 12 }  # matches current frontend call
    """
    name: Optional[str] = None
    role: Optional[Role] = None

    # Nested patches
    hp: Optional[HpPatch] = None
    abilities: Optional[AbilitiesIn] = None

    # Optional flat ability fields (kept to match current frontend PATCH body)
    str: Optional[int] = None
    dex: Optional[int] = None
    con: Optional[int] = None
    int_: Optional[int] = None
    wis: Optional[int] = None
    cha: Optional[int] = None


# ---- Action bodies (unchanged semantics) ----
class PlayerDamageBody(BaseModel):
    damage: int = Field(..., ge=0)


class PlayerHealBody(BaseModel):
    heal: int = Field(..., ge=0)


# ---- Group ----
class GroupStateOut(BaseModel):
    group_id: UUID
    size: int
    max_size: int
