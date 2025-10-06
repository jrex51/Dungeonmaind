from fastapi import APIRouter, HTTPException, status
from uuid import UUID
from app.base_models.schemas import PlayerIn, PlayerOut, GroupStateOut, PlayerHealthPatch, PlayerDamageBody, \
    PlayerHealBody
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
                "hp": player.hp,
                "max_hp": player.max_hp,
                "temp_hp": player.temp_hp,
                "attributes": player.attributes,
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


# Health APIs

@router.patch("/{player_id}/health", response_model=PlayerOut)
async def patch_health(player_id: UUID, patch: PlayerHealthPatch):
    p = await store.get_player(player_id)
    if patch.max_hp is not None or patch.hp is not None or patch.temp_hp is not None:
        p.set_hp(hp = patch.hp if patch.hp is not None else p.hp,
                 max_hp = patch.max_hp if patch.max_hp is not None else p.max_hp,
                 temp_hp = patch.temp_hp if patch.temp_hp is not None else p.temp_hp)
    await store.save_player(p)
    await bus.publish({"type": "health/update", "player_id": str(p.id), "hp": p.hp, "max_hp": p.max_hp, "temp_hp": p.temp_hp})
    return PlayerOut(**p.__dict__)

@router.post("/{player_id}/damage", response_model=PlayerOut)
async def apply_damage(player_id: UUID, body: PlayerDamageBody):
    p = await store.get_player(player_id)
    p.apply_damage(body.damage)
    await store.save_player(p)
    await bus.publish({"type": "health/update", "player_id": str(p.id), "hp": p.hp, "max_hp": p.max_hp, "temp_hp": p.temp_hp})
    return PlayerOut(**p.__dict__)

@router.post("/{player_id}/heal", response_model=PlayerOut)
async def apply_heal(player_id: UUID, body: PlayerHealBody):
    p = await store.get_player(player_id)
    p.heal(body.heal)
    await store.save_player(p)
    await bus.publish({"type": "health/update", "player_id": str(p.id), "hp": p.hp, "max_hp": p.max_hp, "temp_hp": p.temp_hp})
    return PlayerOut(**p.__dict__)


# Attributes APIs

@router.patch("/{player_id}/attributes", response_model=PlayerOut)
async def patch_attributes(player_id: UUID, patch: PlayerHealthPatch):
    p = await store.get_player(player_id)
    # normalize keys to lower-case dnd style
    p.attributes = {k.lower(): int(v) for k, v in patch.attributes.items()}
    await store.save_player(p)
    await bus.publish({"type": "attributes/update", "player_id": str(p.id), "attributes": patch.attributes})
    return PlayerOut(**p.__dict__)