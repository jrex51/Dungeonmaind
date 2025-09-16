import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import run
from app.core.config import settings
from app.core.bus import bus
from app.routers import root, llm, process_audio_data, config_router, health, players, ws_players

# List of available api endpoints
all_routers = [
    (root.router, "", ["root"]),
    (llm.router, "/llm", ["llm"]),
    (process_audio_data.router, "/processAudioData", ["processAudioData"]),
    (config_router.router, "/config", ["config"]),
    (health.router, "/health", ["health"]),
    (players.router, "/players", ["players"]),
    (ws_players.router, "/ws", ["ws"]),
]

# 192.168.x.x und beliebige localhost-Ports zulassen
LAN_REGEX = (
    r"^https?://("                         # http:// oder https://
    r"192\.168\.\d{1,3}\.\d{1,3}"          # 192.168.*.*
    r"|localhost"                          # localhost
    r"|127\.0\.0\.1"                       # 127.0.0.1
    r")(?::\d+)?$"                         # optional :Port
)

def create_app() -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.getLogger("app.bus").info("Starting PresenceBus GC task…")
        await bus.start()
        try:
            yield
        finally:
            logging.getLogger("app.bus").info("Stopping PresenceBus GC task…")
            await bus.stop()

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="1.0.0",
        lifespan=lifespan
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=LAN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register all routers
    for router, prefix, tags in all_routers:
        application.include_router(router, prefix=prefix, tags=tags)

    return application


app = create_app()

if __name__ == "__main__":
    run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_config=None,
    )
