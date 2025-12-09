from fastapi import (
    APIRouter,
    HTTPException,
    status,
    Request,
    Header,
    Depends,
    Query,
    UploadFile,
    File,
)
from uuid import UUID

from app.base_models.schemas import (
    Role,
    PlayerStatus,
    PlayerIn,
    PlayerOut,
    GroupStateOut,
    AbilitiesIn,
    HpPatch,
    PlayerDamageBody,
    PlayerHealBody,
    Hp,
    Abilities,
    MaxHpUpdate,
    JoinCheckOut,
)
from app.domain.models import Player as DomainPlayer
from app.domain.models import Voiceprint
from app.domain.store import store
from app.core.bus import bus

router = APIRouter()


# Helpers

def player_to_out(player: DomainPlayer, request: Request | None = None) -> PlayerOut:
    """
    Map Domain-Player -> PlayerOut.
    Assumes Role/PlayerStatus enums are shared between domain + schemas.
    """
    backend_url = str(request.base_url).rstrip("/") if request is not None else ""

    # Abilities
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

    # HP
    hp_model = Hp(
        current=int(player.hp.current),
        max=int(player.hp.max),
        temp=int(player.hp.temp),
    )

    return PlayerOut(
        id=player.id,
        name=player.name,
        role=player.role,          
        status=player.status,
        created_at=player.created_at,
        last_seen_at=player.last_seen_at,
        backend_url=backend_url,
        hp=hp_model,
        abilities=abilities_model,
    )


async def _get_all_players() -> list[DomainPlayer]:
    """
    Single source to load all players from the domain store.
    Adjust if your store API differs.
    """
    return await store.list_players()



# Group state

@router.get("/state", response_model=GroupStateOut)
async def group_state():
    g = store.group
    return GroupStateOut(group_id=g.id, size=g.size(), max_size=g.max_size())


# List players (with include_inactive)

@router.get("", response_model=list[PlayerOut])
async def list_players(
    request: Request,
    include_inactive: bool = False,
):
    players = await _get_all_players()

    if not include_inactive:
        players = [p for p in players if p.status == PlayerStatus.active]

    return [player_to_out(p, request) for p in players]


# Join check (used by LoginView)

@router.get("/join/check", response_model=JoinCheckOut)
async def join_check(name: str, request: Request):
    players = await _get_all_players()
    target = name.strip().lower()

    # active_conflict
    for p in players:
        if p.name.strip().lower() == target and p.status == PlayerStatus.active:
            return JoinCheckOut(status="active_conflict")

    # inactive_match
    for p in players:
        if p.name.strip().lower() == target and p.status != PlayerStatus.active:
            candidate = player_to_out(p, request)
            return JoinCheckOut(status="inactive_match", candidate=candidate)

    return JoinCheckOut(status="available")


# Join (new + reuse)
@router.post("", response_model=PlayerOut, status_code=status.HTTP_201_CREATED)
async def join(payload: PlayerIn, request: Request):
    # Reuse existing inactive/kicked player
    if payload.reuse_id:
        try:
            p = await store.get_player(payload.reuse_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Player to reuse not found",
            )

        # Leader collision: only one active leader
        if payload.role == Role.leader:
            players = await _get_all_players()
            for other in players:
                if other.id == p.id:
                    continue
                if other.status == PlayerStatus.active and other.role == Role.leader:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Leader role already taken",
                    )

        # Reactivate, update role; keep HP/abilities/name
        p.status = PlayerStatus.active
        p.role = payload.role
        p.touch()
        await store.save_player(p)

        out = player_to_out(p, request)
        await bus.publish({"type": "join", "player": out.model_dump()})
        return out

    # New player
    try:
        player = await store.join(payload.name, payload.role)
    except ValueError as e:
        detail = str(e)
        lowered = detail.lower()
        conflict = (
            "group size" in lowered
            or "group role" in lowered
            or "player name" in lowered
        )
        code = status.HTTP_409_CONFLICT if conflict else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail)

    out = player_to_out(player, request)
    await bus.publish({"type": "join", "player": out.model_dump()})
    return out


# Leave / Kick / Exists

@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave(player_id: UUID):
    await store.leave(player_id)
    await bus.publish({"type": "leave", "player_id": str(player_id)})
    return None


async def _require_leader(
    actor_id: UUID | None = Query(None, alias="actor_id"),
    x_player_id: str | None = Header(default=None, alias="X-Player-Id"),
):
    candidate_ids: list[UUID] = []

    if actor_id:
        candidate_ids.append(actor_id)
    if x_player_id:
        try:
            candidate_ids.append(UUID(x_player_id))
        except ValueError:
            pass

    players = await _get_all_players()

    for cid in candidate_ids:
        for p in players:
            if p.id == cid and p.status == PlayerStatus.active and p.role == Role.leader:
                return p

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Leader permissions required",
    )


@router.post("/{player_id}/kick", status_code=status.HTTP_204_NO_CONTENT)
async def kick(player_id: UUID, _leader=Depends(_require_leader)):
    try:
        p = await store.get_player(player_id)
    except KeyError:
        return None

    p.status = PlayerStatus.kicked
    p.touch()
    await store.save_player(p)

    await bus.kick(player_id)
    await bus.publish({"type": "leave", "player_id": str(player_id)})
    return None


@router.get("/{player_id}/exists")
async def player_exists(player_id: UUID):
    try:
        await store.get_player(player_id)
        return {"exists": True}
    except Exception:
        return {"exists": False}


# Abilities update (self-only)

@router.patch("/{player_id}", response_model=PlayerOut)
async def update_player(
    player_id: UUID,
    payload: AbilitiesIn,
    request: Request,
    x_player_id: str | None = Header(default=None, alias="X-Player-Id"),
):
    if not x_player_id or x_player_id != str(player_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the player can update their own abilities.",
        )

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        p = await store.get_player(player_id)
        return player_to_out(p, request)

    try:
        p = await store.update_player_abilities(player_id, changes)
    except KeyError:
        raise HTTPException(status_code=404, detail="Player not found")

    out = player_to_out(p, request)
    await bus.publish({"type": "update", "player": out.model_dump()})
    return out


# Health APIs (nested hp)

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

@router.post("/{player_id}/voiceprint", response_model=PlayerOut)
async def upload_player_voiceprint(
    player_id: UUID,
    request: Request,
    audio: UploadFile = File(...),
):
    try:
        p = await store.get_player(player_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )

    audio_bytes = await audio.read()
    content_type = audio.content_type
    p.voiceprint = Voiceprint(
        audio_bytes=audio_bytes,
        content_type=content_type,
    )
    await store.save_player(p)

    return player_to_out(p, request)
