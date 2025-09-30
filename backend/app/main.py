import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import run
from app.core.config import settings
from app.routers import root, llm, process_audio_data, config_router, health, players, ws_players, rulebook_markdown

# List of available api endpoints
all_routers = [
    (root.router, "", ["root"]),
    (llm.router, "/llm", ["llm"]),
    (process_audio_data.router, "/processAudioData", ["processAudioData"]),
    (config_router.router, "/config", ["config"]),
    (health.router, "/health", ["health"]),
    (players.router, "/players", ["players"]),
    (ws_players.router, "/ws", ["ws"]),
    #(rulebook_markdown.router, "/folders", ["folders"]),
    #(rulebook_markdown.router, "/file", ["file"]),
    (rulebook_markdown.router, "/rulebook", ["rulebook"]),
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
    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="1.0.0",
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
