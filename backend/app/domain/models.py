from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
import secrets
import string


class Role(str, Enum):
    leader = "leader"
    member = "member"

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

@dataclass
class Player:
    id: UUID
    name: str
    role: Role
    max_hp: int = 10
    hp: int = 10
    temp_hp: int = 0
    attributes: Optional[Dict[str, int]] = None  # {"str": 10, ...}
    created_at: datetime = field(default_factory=now_utc)
    last_seen_at: datetime = field(default_factory=now_utc)

    def touch(self) -> None:
        self.last_seen_at = now_utc()

    # Health helpers
    def clamp(self) -> None:
        if self.max_hp < 1: self.max_hp = 1
        if self.hp > self.max_hp: self.hp = self.max_hp
        if self.hp < 0: self.hp = 0
        if self.temp_hp < 0: self.temp_hp = 0

    def set_hp(self, hp: int, max_hp: Optional[int] = None, temp_hp: Optional[int] = None) -> None:
        if max_hp is not None: self.max_hp = int(max_hp)
        if temp_hp is not None: self.temp_hp = int(temp_hp)
        self.hp = int(hp)
        self.clamp()

    def heal(self, amount: int) -> int:
        before = self.hp
        self.hp = min(self.max_hp, self.hp + max(0, int(amount)))
        return self.hp - before

    def apply_damage(self, dmg: int) -> Dict[str, int]:
        dmg = max(0, int(dmg))
        from_temp = min(self.temp_hp, dmg)
        self.temp_hp -= from_temp
        remaining = dmg - from_temp
        before = self.hp
        self.hp = max(0, self.hp - remaining)
        return {"temp_absorbed": from_temp, "hp_loss": before - self.hp}


@dataclass
class Group:
    id: UUID = field(default_factory=uuid4)
    max_size: int = 6
    # Spieler werden per ID gehalten
    players: Dict[UUID, Player] = field(default_factory=dict)

    def size(self) -> int:
        return len(self.players)

    def leader_id(self) -> Optional[UUID]:
        for pid, p in self.players.items():
            if p.role == Role.leader:
                return pid
        return None

    def has_name(self, name: str) -> bool:
        n = name.strip()
        return any(p.name.lower() == n.lower() for p in self.players.values())

    def add_player(self, name: str, role: Role) -> Player:
        """
        setzt Regeln durch: max. Größe, genau ein Leader.
        """
        if self.size() > self.max_size:
            raise ValueError(f"Group size {self.size} > {self.max_size}")
        if role is Role.leader and self.leader_id() is not None:
            raise ValueError(f"Group role 'leader' already exists")
        if self.has_name(name):
            raise ValueError(f"Player name '{name}' already exists") # eindeutige Namen erzwingen - muss nicht zwingend da ID eindeutig ist, aber angenehmer um Verwechslungen zu vermeiden
        player = Player(id=uuid4(), name=name, role=role)
        self.players[player.id] = player
        return player

    def remove_player(self, pid: UUID) -> None:
        self.players.pop(pid, None)

    def get_player(self, pid: UUID) -> Player:
        p = self.players.get(pid)
        if not p:
            raise KeyError("Player not found.")
        return p

