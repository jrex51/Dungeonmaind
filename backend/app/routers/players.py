from fastapi import APIRouter, HTTPException, status
from uuid import UUID
from app.base_models.schemas import PlayerIn, PlayerOut, GroupStateOut
from app.domain.models import Role as DomainRole
from app.domain.store import store
from app.core.bus import bus

router = APIRouter()

@router.get("/state", response_model=GroupStateOut)
async def group_state():
    g = store.group
    return GroupStateOut(group_id=g.id, size=g.size(), max_size=g.max_size())

@router.get("", response_model=list[PlayerOut])
async def list_players():
    players = await store.list_players()
    return [PlayerOut(**p.__dict__) for p in players]

@router.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def join(payload: PlayerIn):
    try:
        player = await store.join(payload.name, DomainRole(payload.role.value))
        await bus.publish({
            "type": "join",
            "player": {
                "id": str(player.id),
                "name": player.name,
                "role": player.role.value,
            }
        })
    except ValueError as e:
        # Regelverletzung: 400 (oder 409, falls Name/Leader schon vergeben)
        detail = str(e)
        print(detail)
        print(detail.__contains__("Group role"))
        code = status.HTTP_409_CONFLICT if "group size" in detail.lower() or "group role" in detail.lower() or "player name" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, detail=detail)
    return PlayerOut(**player.__dict__)

@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave(player_id: UUID):
    await store.leave(player_id)
    await bus.publish({"type": "leave", "player_id": str(player_id)})
    return None

@router.get("/{player_id}/exists")
async def player_exists(player_id: UUID):
    try:
        player = store.group.players.get(player_id)
        if player is not None:
            print("[CHECK] Player exists")
        else:
            print("[CHECK] Player does not exist")
        return {"exists": player is not None}
    except KeyError:
        print("[CHECK] Player does not exist")
        return {"exists": False}