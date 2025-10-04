from datetime import datetime
from enum import Enum
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
    created_at: datetime
    last_seen_at: datetime
    abilities: Abilities
    backend_url: Optional[str] = None


class GroupStateOut(BaseModel):
    group_id: UUID
    size: int
    max_size: int
