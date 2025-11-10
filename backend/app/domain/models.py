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
    hp: Hp = field(default_factory=Hp)  # nested HP object
    created_at: datetime = field(default_factory=now_utc)
    last_seen_at: datetime = field(default_factory=now_utc)
    abilities: Abilities = field(default_factory=Abilities)


    def touch(self) -> None:
        self.last_seen_at = now_utc()

    # HP helpers

    def clamp(self) -> None:
        if self.hp.max < 1:
            self.hp.max = 1
        if self.hp.current > self.hp.max:
            self.hp.current = self.hp.max
        if self.hp.current < 0:
            self.hp.current = 0
        if self.hp.temp < 0:
            self.hp.temp = 0

    def set_hp(
        self,
        hp: int,
        max_hp: Optional[int] = None,
        temp_hp: Optional[int] = None,
    ) -> None:
        """
        Backwards-kompatible Signatur:
        - hp: neuer current HP
        - max_hp/temp_hp: optional aktualisieren
        """
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
        return {
            "temp_absorbed": from_temp,
            "hp_loss": before - self.hp.current,
        }

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

    # Serialization helpers (tolerate legacy formats)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "role": self.role.value,
            "status": self.status.value,
            "hp": {
                "current": self.hp.current,
                "max": self.hp.max,
                "temp": self.hp.temp,
            },
            "abilities": {
                "str": self.abilities.str,
                "dex": self.abilities.dex,
                "con": self.abilities.con,
                "int_": self.abilities.int_,
                "wis": self.abilities.wis,
                "cha": self.abilities.cha,
            }
            if self.abilities
            else None,
            "created_at": self.created_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        """
        Robust gegen altes Flat-Format:
        - akzeptiert verschachteltes "hp" oder flat "hp/max_hp/temp_hp"
        - akzeptiert "status" sowohl als Enum-Value ("active") als auch als "PlayerStatus.active"
        - abilities optional; defaultet auf sinnvolle Werte
        """
        # Role
        role = Role(data["role"])

        # Status (tolerant)
        status_raw = data.get("status", PlayerStatus.active)
        if isinstance(status_raw, PlayerStatus):
            status = status_raw
        else:
            s = str(status_raw)
            if "." in s:  # handle "PlayerStatus.active"
                s = s.split(".", 1)[1]
            status = PlayerStatus(s)

        # HP: nested or flat
        hp_field = data.get("hp")
        if isinstance(hp_field, dict):
            hp = Hp(
                current=int(hp_field.get("current", 10)),
                max=int(hp_field.get("max", 10)),
                temp=int(hp_field.get("temp", 0)),
            )
        else:
            hp = Hp(
                current=int(data.get("hp", 10)),
                max=int(data.get("max_hp", 10)),
                temp=int(data.get("temp_hp", 0)),
            )

        # Abilities
        abilities_data = data.get("abilities") or {}
        abilities = Abilities(
            str=int(abilities_data.get("str", 10)),
            dex=int(abilities_data.get("dex", 10)),
            con=int(abilities_data.get("con", 10)),
            int_=int(abilities_data.get("int_", 10)),
            wis=int(abilities_data.get("wis", 10)),
            cha=int(abilities_data.get("cha", 10)),
        )

        created_at = (
            datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else now_utc()
        )
        last_seen_at = (
            datetime.fromisoformat(data["last_seen_at"])
            if "last_seen_at" in data
            else created_at
        )

        return cls(
            id=UUID(str(data["id"])),
            name=data["name"],
            role=role,
            status=status,
            hp=hp,
            abilities=abilities,
            created_at=created_at,
            last_seen_at=last_seen_at,
        )


@dataclass
class Group:
    id: UUID = field(default_factory=uuid4)
    max_size: int = 6
    # Spieler werden per ID gehalten
    players: Dict[UUID, Player] = field(default_factory=dict)

    # Views 

    def active(self) -> Dict[UUID, Player]:
        """Nur aktive Spieler."""
        return {
            pid: p
            for pid, p in self.players.items()
            if p.status == PlayerStatus.active
        }

    def size(self) -> int:
        """Aktuelle Gruppengröße = nur aktive Spieler."""
        return len(self.active())

    def leader_id(self) -> Optional[UUID]:
        """Aktiver Leader, falls vorhanden."""
        for pid, p in self.active().items():
            if p.role == Role.leader:
                return pid
        return None

    def has_active_name(self, name: str) -> bool:
        """Eindeutiger Name unter aktiven Spielern."""
        n = name.strip().lower()
        return any(
            p.name.strip().lower() == n
            for p in self.active().values()
        )

    # Mutations

    def add_player(self, name: str, role: Role) -> Player:
        """
        Regeln:
        - max. Größe (nur aktive Spieler zählen)
        - maximal ein aktiver Leader
        - eindeutige Namen unter aktiven Spielern
        """
        if self.size() >= self.max_size:
            raise ValueError(f"Group size {self.size()} >= {self.max_size}")
        if role is Role.leader and self.leader_id() is not None:
            raise ValueError("Group role 'leader' already exists")
        if self.has_active_name(name):
            raise ValueError(f"Player name '{name}' already exists")

        player = Player(
            id=uuid4(),
            name=name,
            role=role,
            status=PlayerStatus.active,
        )
        self.players[player.id] = player
        return player

    def deactivate(
        self,
        pid: UUID,
        status: PlayerStatus = PlayerStatus.inactive,
    ) -> None:
        """
        Spieler "soft" deaktivieren:
        - Status anpassen
        - last_seen_at aktualisieren
        - bei Status==inactive Duplikate (inactive/kicked) mit gleichem Namen aufräumen
        """
        p = self.players.get(pid)
        if not p:
            return

        p.status = status
        p.touch()

        if status == PlayerStatus.inactive:
            n = p.name.strip().lower()
            to_remove = [
                other_id
                for other_id, other in self.players.items()
                if other_id != pid
                and other.status in (PlayerStatus.inactive, PlayerStatus.kicked)
                and other.name.strip().lower() == n
            ]
            for other_id in to_remove:
                self.players.pop(other_id, None)

    def reactivate(self, pid: UUID) -> Player:
        """
        Spieler wieder aktiv setzen.
        """
        p = self.players.get(pid)
        if not p:
            raise KeyError(f"Player '{pid}' does not exist")
        p.status = PlayerStatus.active
        p.touch()
        return p

    def get_player(self, pid: UUID) -> Player:
        p = self.players.get(pid)
        if not p:
            raise KeyError("Player not found.")
        return p

    def remove_player(self, pid: UUID) -> None:
        """
        Für Altcode:
        nicht hart löschen, sondern als inaktiv markieren.
        """
        self.deactivate(pid, status=PlayerStatus.inactive)
