import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import run
from app.core.config import settings
from app.functions.embedding.embedding_model import embedd_rulebook, read_text_files, delete_chromadb
from app.routers import root, llm, process_audio_data, config_router, health, players, ws_players, rulebook_markdown, export_import_session
from contextlib import asynccontextmanager

# List of available api endpoints
all_routers = [
    (root.router, "", ["root"]),
    (llm.router, "/llm", ["llm"]),
    (process_audio_data.router, "/processAudioData", ["processAudioData"]),
    (config_router.router, "/config", ["config"]),
    (health.router, "/health", ["health"]),
    (players.router, "/players", ["players"]),
    (ws_players.router, "/ws", ["ws"]),
    (rulebook_markdown.router, "/rulebook", ["rulebook"]),
    (export_import_session.router, "/exportImport", ["exportImport"]),
]

# 192.168.x.x und beliebige localhost-Ports zulassen
LAN_REGEX = (
    r"^https?://("                         # http:// oder https://
    r"192\.168\.\d{1,3}\.\d{1,3}"          # 192.168.*.*
    r"|localhost"                          # localhost
    r"|127\.0\.0\.1"                       # 127.0.0.1
    r")(?::\d+)?$"                         # optional :Port
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logging.info("Server starting: deleting old ChromaDB and re-embedding rulebook...")
    delete_chromadb()

    # Rulebook embedding
    texts, txt_paths = read_text_files()
    embedd_rulebook(texts, txt_paths)
    logging.info("Rulebook successfully embedded.")

    yield  # ← Server running

    # Shutdown logic
    logging.info("Server Dungeonmaind shutting down...")

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
        lifespan=lifespan,
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
