"""Atomic JSON persistence for the current session's geographic map."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from app.base_models.map_models import MapData


class MapStore:
    def __init__(self, file_path: str | Path) -> None:
        # Reading an absent map must not create session data.
        self.file_path = Path(file_path)
        self._lock = Lock()

    def get_map(self) -> MapData:
        with self._lock:
            if not self.file_path.exists():
                return MapData()
            # Corrupt saved data is an error, never silently an empty graph.
            return MapData.model_validate_json(
                self.file_path.read_text(encoding="utf-8")
            )

    def replace_map(self, map_data: MapData) -> MapData:
        # Revalidate even an existing model: callers can mutate it after creation.
        validated = MapData.model_validate(map_data.model_dump(mode="json"))
        payload = json.dumps(
            validated.model_dump(mode="json"), indent=2, ensure_ascii=False
        )
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                # Use the destination directory so replacement stays atomic.
                with NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.file_path.parent,
                    prefix="map-", suffix=".tmp", delete=False,
                ) as file:
                    temporary = Path(file.name)
                    file.write(payload)
                    file.flush()
                    os.fsync(file.fileno())
                # Close before replacing, including on Windows.
                os.replace(temporary, self.file_path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return validated

    def clear_map(self) -> MapData:
        return self.replace_map(MapData())
