import asyncio
from uuid import UUID
from typing import Mapping, Optional
from app.domain.models import Group, Player, Role


class SingleGroupStore:
    """
    Thread-/Task-sicherer Zugriff auf die Gruppe
    """

    def __init__(self) -> None:
        self.group = Group()
        self._lock = asyncio.Lock()

    async def join(self, name: str, role: Role) -> Player:
        async with self._lock:
            return self.group.add_player(name, role)

    async def leave(self, player_id: UUID) -> None:
        async with self._lock:
            self.group.remove_player(player_id)

    async def list_players(self) -> list[Player]:
        # bewusst kein lock auf die list, da vermutlich nicht so viele Anfragen
        return list(self.group.players.values())

    async def get_player(self, player_id: UUID) -> Player:
        async with self._lock:
            return self.group.get_player(player_id)

    # Abilities Update für einen Spieler
    async def update_player_abilities(
        self,
        player_id: UUID,
        changes: Mapping[str, Optional[int]],
    ) -> Player:
        """
        Aktualisiert die übergebenen Ability-Felder (str/dex/con/int_/wis/cha).
        'changes' enthält nur die Keys, die geändert werden sollen.
        """
        async with self._lock:
            p = self.group.get_player(player_id)  # KeyError falls unbekannt
            for k, v in changes.items():
                if v is None:
                    continue
                # nur bekannte Ability-Felder setzen
                if hasattr(p.abilities, k):
                    setattr(p.abilities, k, int(v))
            p.touch()
            return p

    async def save_player(self, player: Player) -> None:
        async with self._lock:
            self.group.players[player.id] = player


store = SingleGroupStore()
