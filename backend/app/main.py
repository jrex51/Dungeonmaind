import sys, asyncio

from aiohttp.hdrs import ACCESS_CONTROL_ALLOW_ORIGIN

# On windows its possible to run into race conditions when using asyncio.
# Setting the EventLoopPolicy here will prevent async race conditions.
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import run
from app.core.config import settings
from app.functions.embedding.embedding_model import (embedd_rulebook, read_text_files, delete_chromadb,
                                                     delete_transcription_embeddings, has_rulebook_embeddings)
from app.routers import (root, llm, process_audio_data, config_router, health, players, ws_players, rulebook_markdown,
                         export_import_session)
from contextlib import asynccontextmanager
from app.core.bus import bus

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
    # Check if this deletes everything. Should just delete the tmp folders and for the main db just delete transcriptions
    delete_chromadb(True, False)

    logging.getLogger("app.bus").info("Starting PresenceBus GC task…")
    await bus.start()

    # Rulebook embedding
    # Here check first if the rulebook embeddings are still present in the main db. If not for some reason we add them again. This will also happen
    # on the very first start up of the application
    if not has_rulebook_embeddings():
        texts, txt_paths = read_text_files()
        embedd_rulebook(texts, txt_paths)
        logging.info("Rulebook successfully embedded.")
        print("Rulebook successfully embedded.")
    delete_transcription_embeddings()

    try:
        yield  # Server running
    finally:
        # Shutdown logic
        # Keep the main db, just delete the tmp bases
        delete_chromadb(True, True)
        logging.getLogger("app.bus").info("Stopping PresenceBus GC task…")
        await bus.stop()
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
