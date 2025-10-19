from datetime import datetime
from enum import Enum
from typing import Optional, Dict
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field


class Role(str, Enum):
    leader = "leader"
    member = "member"


class PlayerIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    role: Role


class Abilities(BaseModel):
    str: int = Field(..., alias="str")
    dex: int = Field(..., alias="dex")
    con: int = Field(..., alias="con")
    int_: int = Field(..., alias="int_")
    wis: int = Field(..., alias="wis")
    cha: int = Field(..., alias="cha")


class AbilitiesIn(BaseModel):
    str: Optional[int] = Field(None, alias="str")
    dex: Optional[int] = Field(None, alias="dex")
    con: Optional[int] = Field(None, alias="con")
    int_: Optional[int] = Field(None, alias="int_")
    wis: Optional[int] = Field(None, alias="wis")
    cha: Optional[int] = Field(None, alias="cha")


class PlayerOut(BaseModel):
    id: UUID
    name: str
    role: Role
    max_hp: int = 10
    hp: int = 0
    temp_hp: int = 0
    created_at: datetime
    last_seen_at: datetime
    abilities: Abilities
    backend_url: Optional[str] = None


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
