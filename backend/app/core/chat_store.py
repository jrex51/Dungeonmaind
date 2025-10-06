import asyncio
from collections import defaultdict
from uuid import UUID

class ChatStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._by_player = defaultdict(list)  # UUID -> List[dict]

    async def append(self, player_id: UUID, role: str, content: str) -> None:
        async with self._lock:
            self._by_player[player_id].append({"role": role, "content": content})

    async def history(self, player_id: UUID) -> list[dict]:
        # Nur Kopie rausgeben
        async with self._lock:
            return list(self._by_player[player_id])

    async def clear(self, player_id: UUID) -> None:
        async with self._lock:
            self._by_player[player_id].clear()

chat_store = ChatStore()


