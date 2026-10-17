import json
import os
from datetime import datetime, timezone
from threading import Lock
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
from pydantic import TypeAdapter

from app.base_models.timeline_models import (
    TimelineEvent,
    TimelineEventCreate,
    TimelineEventUpdate,
)
from app.core.config import settings


class TimelineStore:
    """
    JSON-backed storage for timeline events.

    This is intentionally lightweight and appropriate for the current
    single-session Dungeonmaind application. The storage layer can later
    be replaced by a database without changing the API models.
    """

    def __init__(self, file_path: str | Path | None = None) -> None:
        self.file_path = str(file_path) if file_path is not None else os.path.join(
            settings.backend_root_path,
            "data",
            "timeline_events.json",
        )

        self._lock = Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        os.makedirs(
            os.path.dirname(self.file_path),
            exist_ok=True,
        )

        if not os.path.exists(self.file_path):
            self._write_events([])

    def _read_events(self) -> list[TimelineEvent]:
        try:
            with open(
                self.file_path,
                "r",
                encoding="utf-8",
            ) as file:
                raw_events = json.load(file)

            return [
                TimelineEvent.model_validate(event)
                for event in raw_events
            ]

        except (
            FileNotFoundError,
            json.JSONDecodeError,
            ValueError,
        ):
            return []

    def _write_events(
        self,
        events: list[TimelineEvent],
    ) -> None:
        temporary_path = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=Path(self.file_path).parent,
                prefix="timeline-", suffix=".tmp", delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump([event.model_dump(mode="json") for event in events],
                          file, indent=2, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self.file_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def load_snapshot(file_path: str | Path) -> list[TimelineEvent]:
        """Strictly validate saved data without constructing/writing a store."""
        path = Path(file_path)
        if not path.exists():
            return []  # Legacy sessions have no timeline snapshot.
        return TypeAdapter(list[TimelineEvent]).validate_json(path.read_text(encoding="utf-8"))

    def snapshot(self) -> list[TimelineEvent]:
        with self._lock:
            return self.load_snapshot(self.file_path)

    def replace_snapshot(self, events: list[TimelineEvent]) -> list[TimelineEvent]:
        """Restore a validated snapshot, preserving IDs and both timestamps."""
        validated = TypeAdapter(list[TimelineEvent]).validate_python(
            [event.model_dump(mode="json") for event in events]
        )
        with self._lock:
            self._write_events(validated)
        return validated

    def list_events(self) -> list[TimelineEvent]:
        with self._lock:
            events = self._read_events()

        return sorted(
            events,
            key=lambda event: (
                event.start_time,
                event.end_time,
                event.created_at,
            ),
        )

    def get_event(
        self,
        event_id: str,
    ) -> TimelineEvent | None:
        return next(
            (
                event
                for event in self.list_events()
                if event.id == event_id
            ),
            None,
        )

    def create_event(
        self,
        event_data: TimelineEventCreate,
    ) -> TimelineEvent:
        now = datetime.now(timezone.utc).isoformat()

        event = TimelineEvent(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            **event_data.model_dump(),
        )

        with self._lock:
            events = self._read_events()
            events.append(event)
            self._write_events(events)

        return event

    def update_event(
        self,
        event_id: str,
        update_data: TimelineEventUpdate,
    ) -> TimelineEvent | None:
        with self._lock:
            events = self._read_events()

            for index, event in enumerate(events):
                if event.id != event_id:
                    continue

                updated_values = update_data.model_dump(
                    exclude_unset=True,
                )

                updated_values["updated_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )

                updated_event = event.model_copy(
                    update=updated_values,
                )

                events[index] = updated_event
                self._write_events(events)

                return updated_event

        return None

    def delete_event(
        self,
        event_id: str,
    ) -> bool:
        with self._lock:
            events = self._read_events()

            remaining_events = [
                event
                for event in events
                if event.id != event_id
            ]

            if len(remaining_events) == len(events):
                return False

            self._write_events(remaining_events)
            return True

    def replace_events(
        self,
        event_data: list[TimelineEventCreate],
    ) -> list[TimelineEvent]:
        now = datetime.now(timezone.utc).isoformat()

        events = [
            TimelineEvent(
                id=str(uuid4()),
                created_at=now,
                updated_at=now,
                **item.model_dump(),
            )
            for item in event_data
        ]

        with self._lock:
            self._write_events(events)

        return self.list_events()

    def clear_events(self) -> None:
        with self._lock:
            self._write_events([])


timeline_store = TimelineStore()
