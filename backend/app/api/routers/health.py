from fastapi import APIRouter, Response, status

router = APIRouter()


@router.get("/checkConnection")
async def checkConnection(response: Response):
    print("check_connection: Habe Anfrage erhalten!")
    response.status_code = status.HTTP_204_NO_CONTENT
    response.headers["Cache-Control"] = "no-store"  # Caching unterbinden - wichtig, damit Browser/Proxies nichts "alt" liefern.



