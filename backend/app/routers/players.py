from fastapi import APIRouter, HTTPException, status, Request, Header
from uuid import UUID
from app.base_models.schemas import (
    PlayerIn,
    PlayerOut,
    GroupStateOut,
    AbilitiesIn,
    HpPatch,
    PlayerDamageBody,
    PlayerHealBody,
    Hp,
    Abilities,
    MaxHpUpdate
)
from app.domain.models import Role as DomainRole
from app.domain.store import store
from app.core.bus import bus

router = APIRouter()


def player_to_out(player, request: Request | None = None) -> PlayerOut:
    """
    Konvertiert Domain-Player -> PlayerOut (mit verschachteltem hp und abilities)
    """
    backend_url = str(request.base_url).rstrip("/") if request is not None else ""

    abilities_model = None
    if getattr(player, "abilities", None) is not None:
        a = player.abilities
        abilities_model = Abilities(
            str=int(getattr(a, "str")),
            dex=int(getattr(a, "dex")),
            con=int(getattr(a, "con")),
            int_=int(getattr(a, "int_")),
            wis=int(getattr(a, "wis")),
            cha=int(getattr(a, "cha")),
        )

    hp_model = Hp(
        current=int(player.hp.current),
        max=int(player.hp.max),
        temp=int(player.hp.temp),
    )

    return PlayerOut(
        id=player.id,
        name=player.name,
        role=player.role.value if hasattr(player.role, "value") else str(player.role),
        created_at=player.created_at,
        last_seen_at=player.last_seen_at,
        backend_url=backend_url,
        hp=hp_model,
        abilities=abilities_model,
    )



@router.get("/state", response_model=GroupStateOut)
async def group_state():
    g = store.group
    return GroupStateOut(group_id=g.id, size=g.size(), max_size=g.max_size())


@router.get("", response_model=list[PlayerOut])
async def list_players(request: Request):
    players = await store.list_players()
    return [player_to_out(p, request) for p in players]


@router.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def join(payload: PlayerIn, request: Request):
    try:
        player = await store.join(payload.name, DomainRole(payload.role.value))
        out = player_to_out(player, request)
        # Live-Update: kompletter Spieler inkl. abilities und verschachteltem hp
        await bus.publish({
            "type": "join",
            "player": out.model_dump(),
        })
    except ValueError as e:
        # Regelverletzung: 400 (oder 409, falls Name/Leader schon vergeben)
        detail = str(e)
        code = (
            status.HTTP_409_CONFLICT
            if "group size" in detail.lower()
            or "group role" in detail.lower()
            or "player name" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(code, detail=detail)
    return out


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave(player_id: UUID):
    await store.leave(player_id)
    await bus.publish({"type": "leave", "player_id": str(player_id)})
    return None


@router.patch("/{player_id}", response_model=PlayerOut)
async def update_player(
    player_id: UUID,
    payload: AbilitiesIn,
    request: Request,
    x_player_id: str | None = Header(default=None, alias="X-Player-Id"),
):
    # Simple Self-Permission: nur der eigene Spieler darf sich ändern
    if not x_player_id or x_player_id != str(player_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the player can update their own abilities.",
        )

    # Änderungen extrahieren (nur gesetzte Felder)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        # Nichts zu tun, gib aktuellen Stand zurück
        p = await store.get_player(player_id)
        return player_to_out(p, request)

    try:
        p = await store.update_player_abilities(player_id, changes)
    except KeyError:
        raise HTTPException(status_code=404, detail="Player not found")

    out = player_to_out(p, request)
    # WS-Live-Update an alle (vollständiger Player)
    await bus.publish({"type": "update", "player": out.model_dump()})
    return out


# Health APIs

@router.patch("/{player_id}/health", response_model=PlayerOut)
async def patch_health(player_id: UUID, patch: HpPatch, request: Request):
    p = await store.get_player(player_id)

    if patch.current is not None:
        p.hp.current = int(patch.current)
    if patch.max is not None:
        p.hp.max = int(patch.max)
    if patch.temp is not None:
        p.hp.temp = int(patch.temp)
    p.clamp()
    await store.save_player(p)

    await bus.publish({
        "type": "health/update",
        "player_id": str(p.id),
        "hp": {
            "current": p.hp.current,
            "max": p.hp.max,
            "temp": p.hp.temp,
        },
    })
    return player_to_out(p, request)


@router.post("/{player_id}/damage", response_model=PlayerOut)
async def apply_damage(player_id: UUID, body: PlayerDamageBody, request: Request):
    p = await store.get_player(player_id)
    p.apply_damage(body.damage)
    await store.save_player(p)
    await bus.publish({
        "type": "health/update",
        "player_id": str(p.id),
        "hp": {
            "current": p.hp.current,
            "max": p.hp.max,
            "temp": p.hp.temp,
        },
    })
    return player_to_out(p, request)


@router.post("/{player_id}/heal", response_model=PlayerOut)
async def apply_heal(player_id: UUID, body: PlayerHealBody, request: Request):
    p = await store.get_player(player_id)
    p.heal(body.heal)
    await store.save_player(p)
    await bus.publish({
        "type": "health/update",
        "player_id": str(p.id),
        "hp": {
            "current": p.hp.current,
            "max": p.hp.max,
            "temp": p.hp.temp,
        },
    })
    return player_to_out(p, request)

@router.post("/{player_id}/health/max", response_model=PlayerOut)
async def update_max_hp(player_id: UUID, body: MaxHpUpdate, request: Request):
    try:
        p = await store.update_player_max_hp(player_id, body.max)
    except KeyError:
        raise HTTPException(status_code=404, detail="Player not found")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Notify all listeners so UIs stay in sync
    await bus.publish({
        "type": "health/update",
        "player_id": str(p.id),
        "hp": {
            "current": p.hp.current,
            "max": p.hp.max,
            "temp": p.hp.temp,
        },
    })

    return player_to_out(p, request)

