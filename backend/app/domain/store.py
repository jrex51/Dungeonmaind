import asyncio
from uuid import UUID
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
        return list(self.group.players.values())  # bewusst kein lock auf die list, da vermutlich nicht so viele Anfragen

store = SingleGroupStore()
