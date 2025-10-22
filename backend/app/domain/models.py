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

def make_join_code(length: int = 6) -> str:
    """
    Kurzer, menschenlesbarer Code (z.B. 'AB3FQ7') für den Gruppeneinstieg.
    """
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

@dataclass
class Player:
    id: UUID
    name: str
    role: Role
    created_at: datetime = field(default_factory=now_utc)
    last_seen_at: datetime = field(default_factory=now_utc)

    def touch(self) -> None:
        self.last_seen_at = now_utc()

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

    #def get_players(self) -> Dict[UUID, Player]:
    #    p = self.players
    #    if not p:
    #        raise KeyError("Player not found.")
    #    return p

