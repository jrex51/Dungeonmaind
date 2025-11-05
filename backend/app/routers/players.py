from fastapi import APIRouter, HTTPException, status, Depends, Query
from uuid import UUID
from app.base_models.schemas import PlayerIn, PlayerOut, GroupStateOut, PlayerHealthPatch, PlayerDamageBody, \
    PlayerHealBody, JoinCheckOut
from app.domain.models import Role, PlayerStatus, Player
from app.domain.store import store
from app.core.bus import bus

router = APIRouter()

# Helpers

def player_out(p: Player) -> dict:
    # dict nur für WS-Events
    return {
        "id": str(p.id),
        "name": p.name,
        "role": p.role.value if isinstance(p.role, Role) else str(p.role),
        "hp": p.hp,
        "max_hp": p.max_hp,
        "temp_hp": p.temp_hp,
        "attributes": p.attributes,
        "status": p.status.value if isinstance(p.status, PlayerStatus) else str(p.status),
        "created_at": p.created_at.isoformat(),
        "last_seen_at": p.last_seen_at.isoformat(),
    }


def require_leader(actor_id: UUID | None = Query(None)):
    if actor_id:
        try:
            p = store.group.get_player(actor_id)
            if p.role == Role.leader and p.status == PlayerStatus.active:
                return p
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Leader permissions required")

    lid = store.group.leader_id()
    if lid:
        return store.group.get_player(lid)

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Leader not found")

# APIs

@router.get("/state", response_model=GroupStateOut)
async def group_state():
    g = store.group
    return GroupStateOut(group_id=g.id, size=g.size(), max_size=g.max_size())

@router.get("", response_model=list[PlayerOut])
async def list_players(include_inactive: bool = False):
    players = (store.group.players.values() if include_inactive else store.group.active().values())
    return [PlayerOut(**p.__dict__) for p in players]

@router.get("/join/check", response_model=JoinCheckOut)
async def join_check(name: str):
    # falls aktiver Name belegt -> active_conflict
    if store.group.has_active_name(name):
        return JoinCheckOut(status="active_conflict")

    # inaktive mit gleichem Namen vorhanden
    cand = next((p for p in store.group.players.values()
                 if p.name.lower()==name.strip().lower() and p.status!=PlayerStatus.active), None)
    if cand:
        return JoinCheckOut(status="inactive_match", candidate=PlayerOut(**cand.__dict__))
    return JoinCheckOut(status="available")

@router.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def join(payload: PlayerIn):
    # Re-Join
    if payload.reuse_id:
        print("reuse_id wurde übergeben")
        try:
            p = store.group.reactivate(payload.reuse_id)
        except KeyError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Player to reuse not found")
        if payload.role == Role.leader:
            current_leader_id = store.group.leader_id()
            if current_leader_id is not None and current_leader_id != p.id:
                raise HTTPException(409, detail=f"Leader role already taken")

        p.role = payload.role
        store.group.reactivate(p.id)
        await bus.publish({ "type": "join", "player": player_out(p) })
        return PlayerOut(**p.__dict__)


    # neu anlegen (prüft nur aktive auf Kollision)
    try:
        p = store.group.add_player(payload.name, payload.role)
        await bus.publish({"type":"join","player": player_out(p)})
        return PlayerOut(**p.__dict__)
    except ValueError as e:
        # Regelverletzung: 400 (oder 409, falls Name/Leader schon vergeben)
        detail = str(e)
        print(detail)
        print(detail.__contains__("Group role"))
        code = status.HTTP_409_CONFLICT if "group size" in detail.lower() or "group role" in detail.lower() or "player name" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, detail=detail)

@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave(player_id: UUID):
    store.group.deactivate(player_id, status=PlayerStatus.inactive)
    await bus.publish({"type": "leave", "player_id": str(player_id)})
    return None

@router.post("/{player_id}/kick", status_code=status.HTTP_204_NO_CONTENT)
async def kick(player_id: UUID, _leader=Depends(require_leader)):
    # Status -> kicked (damit sichtbar, dass es absichtlich war)
    store.group.deactivate(player_id, status=PlayerStatus.kicked)
    # Sockets schließen & Broadcast
    await bus.kick(player_id) # schließt alle WS des Spielers
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

