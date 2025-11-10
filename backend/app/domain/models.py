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


class PlayerStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    kicked = "kicked"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def make_join_code(length: int = 6) -> str:
    """
    Kurzer, menschenlesbarer Code (z.B. 'AB3FQ7') für den Gruppeneinstieg.
    """
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@dataclass
class Abilities:
    # stabile numerische Defaults, damit das Frontend keine "—" zeigt
    str: int = 10
    dex: int = 10
    con: int = 10
    int_: int = 10
    wis: int = 10
    cha: int = 10


@dataclass
class Hp:
    current: int = 10
    max: int = 10
    temp: int = 0


@dataclass
class Player:
    id: UUID
    name: str
    role: Role
    status: PlayerStatus = PlayerStatus.active
    hp: Hp = field(default_factory=Hp)  # nested HP object to mirror frontend
    created_at: datetime = field(default_factory=now_utc)
    last_seen_at: datetime = field(default_factory=now_utc)
    abilities: Abilities = field(default_factory=Abilities)

    def touch(self) -> None:
        self.last_seen_at = now_utc()

    # Health helpers
    def clamp(self) -> None:
        if self.hp.max < 1:
            self.hp.max = 1
        if self.hp.current > self.hp.max:
            self.hp.current = self.hp.max
        if self.hp.current < 0:
            self.hp.current = 0
        if self.hp.temp < 0:
            self.hp.temp = 0

    def set_hp(self, hp: int, max_hp: Optional[int] = None, temp_hp: Optional[int] = None) -> None:
        # Keep parameter names for backwards-compat at call sites
        if max_hp is not None:
            self.hp.max = int(max_hp)
        if temp_hp is not None:
            self.hp.temp = int(temp_hp)
        self.hp.current = int(hp)
        self.clamp()

    def heal(self, amount: int) -> int:
        before = self.hp.current
        self.hp.current = min(self.hp.max, self.hp.current + max(0, int(amount)))
        return self.hp.current - before

    def apply_damage(self, dmg: int) -> Dict[str, int]:
        dmg = max(0, int(dmg))
        from_temp = min(self.hp.temp, dmg)
        self.hp.temp -= from_temp
        remaining = dmg - from_temp
        before = self.hp.current
        self.hp.current = max(0, self.hp.current - remaining)
        return {"temp_absorbed": from_temp, "hp_loss": before - self.hp.current}

    def set_max_hp(self, max_hp: int) -> None:
        """
        Set max HP and keep all HP values in a valid range.
        - max_hp must be >= 1
        - current is clamped down if above new max
        """
        max_hp_int = int(max_hp)
        if max_hp_int < 1:
            raise ValueError("max_hp must be at least 1")

        self.hp.max = max_hp_int
        self.clamp()



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
            raise ValueError(
                f"Player name '{name}' already exists"
            )  # eindeutige Namen erzwingen - muss nicht zwingend da ID eindeutig ist, aber angenehmer um Verwechslungen zu vermeiden
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
