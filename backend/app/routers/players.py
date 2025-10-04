from fastapi import APIRouter, HTTPException, status, Request, Header
from uuid import UUID
from app.base_models.schemas import PlayerIn, PlayerOut, GroupStateOut, AbilitiesIn
from app.domain.models import Role as DomainRole
from app.domain.store import store
from app.core.bus import bus

router = APIRouter()


def player_to_out(player, request: Request | None = None) -> PlayerOut:
    """
    Konvertiert Domain-Player -> PlayerOut
    """
    backend_url = str(request.base_url).rstrip("/") if request is not None else ""
    abilities = None
    if hasattr(player, "abilities") and player.abilities is not None:
        try:
            abilities = {
                "str": int(getattr(player.abilities, "str")),
                "dex": int(getattr(player.abilities, "dex")),
                "con": int(getattr(player.abilities, "con")),
                "int_": int(getattr(player.abilities, "int_")),
                "wis": int(getattr(player.abilities, "wis")),
                "cha": int(getattr(player.abilities, "cha")),
            }
        except Exception:
            # Fallback, falls abilities bereits dict-artig ist
            a = getattr(player, "abilities", {}) or {}
            abilities = {
                "str": int(a.get("str")) if a.get("str") is not None else None,
                "dex": int(a.get("dex")) if a.get("dex") is not None else None,
                "con": int(a.get("con")) if a.get("con") is not None else None,
                "int_": int(a.get("int_")) if a.get("int_") is not None else None,
                "wis": int(a.get("wis")) if a.get("wis") is not None else None,
                "cha": int(a.get("cha")) if a.get("cha") is not None else None,
            }

    return PlayerOut(
        id=player.id,
        name=player.name,
        role=player.role.value if hasattr(player.role, "value") else str(player.role),
        created_at=player.created_at,
        last_seen_at=player.last_seen_at,
        backend_url=backend_url,
        abilities=abilities,
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
        # Live-Update: kompletter Spieler inkl. abilities
        await bus.publish({
            "type": "join",
            "player": out.model_dump()
        })
    except ValueError as e:
        # Regelverletzung: 400 (oder 409, falls Name/Leader schon vergeben)
        detail = str(e)
        code = status.HTTP_409_CONFLICT if "group size" in detail.lower() or "group role" in detail.lower() or "player name" in detail.lower() else status.HTTP_400_BAD_REQUEST
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the player can update their own abilities.")

    # Änderungen extrahieren (nur gesetzte Felder)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        # Nichts zu tun, gib aktuellen Stand zurück
        players = await store.list_players()
        p = next((pp for pp in players if str(pp.id) == str(player_id)), None)
        if not p:
            raise HTTPException(status_code=404, detail="Player not found")
        out = player_to_out(p, request)
        return out

    try:
        p = await store.update_player_abilities(player_id, changes)
    except KeyError:
        raise HTTPException(status_code=404, detail="Player not found")

    out = player_to_out(p, request)
    # WS-Live-Update an alle
    await bus.publish({"type": "update", "player": out.model_dump()})
    return out