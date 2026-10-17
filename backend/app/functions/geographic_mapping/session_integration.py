"""Explicit lifecycle coordination for the existing single-worker backend.

All HTTP operations that change transcripts, timelines or sessions share one
async lock with map generation. Reads use only their store lock. Cancellation
waits for a started mutation to finish: cancelling to_thread cannot stop its
worker, and releasing the lifecycle lock early would permit stale writes.
This is process-local coordination, not a multi-worker or database transaction.

Saved sessions carry geographic_map.json and timeline_events.json. Both append
and replacement clear active views; a failed preflight preserves them. Once a
legacy import/deletion starts, failed partial mutations leave empty views.
There is no reliable active-session ID, so any valid deletion invalidates them.
Group/settings/Chroma imports remain nontransactional. Exports publish validated
sibling directories with rollback. Crash recovery and out-of-process file edits
are outside this lock's scope.
Imported Chroma uses a temporary copy and an in-memory path. A marker invalidates
its active views on the next startup, before existing cleanup removes that copy;
saved-session snapshots remain available for re-import. Ordinary stored views
survive restart as before.
"""

import asyncio
from functools import lru_cache
from pathlib import Path

from app.functions.geographic_mapping.map_store import MapStore


class SessionLifecycle:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def run(self, operation):
        async with self._lock:
            task = asyncio.create_task(operation())
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Keep ownership until even a blocking worker has stopped.
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not task.cancelled():
                    task.exception()  # Retrieve any failure after cancellation.
                raise


@lru_cache(maxsize=1)
def get_lifecycle() -> SessionLifecycle:
    return SessionLifecycle()


@lru_cache(maxsize=1)
def get_map_store() -> MapStore:
    from app.core.config import settings

    return MapStore(Path(settings.backend_root_path) / "data" / "geographic_map.json")


def get_timeline_store():
    from app.functions.timeline.timeline_store import timeline_store

    return timeline_store


def clear_views():
    """Call under the lifecycle lock before a potentially partial mutation.

    Both append and replacement invalidate the complete generated timeline:
    neither view has a partial-update or stale-state contract in the frontend.
    """
    get_map_store().clear_map()
    get_timeline_store().clear_events()


def begin_session_import():
    # Mark before any partial mutation, including an interrupted/failed import.
    marker = Path(get_timeline_store().file_path).with_name("imported_session_views.flag")
    marker.touch()
    clear_views()


def invalidate_imported_views_on_startup():
    marker = Path(get_timeline_store().file_path).with_name("imported_session_views.flag")
    if marker.exists():
        clear_views()
        marker.unlink()
