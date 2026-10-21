"""SQLite 저장소 (순수 표준 라이브러리 ``sqlite3``).

세 가지 테이블을 관리합니다.

- ``events``        : 웹 UI 로 관리하는 팀 일정 (CRUD 대상)
- ``seen_events``   : 기존 JSON "이미 본 일정" 상태를 대체하는 SQLite 버전
- ``notifications`` : 웹에서 발생한 알림/변경 내역 (최근 알림 내역 페이지용)

도메인 모델(:class:`team_schedule.models.Event`) 과 상호 변환하므로
겹침 탐지(`overlap`)·요약(`summary`) 등 기존 로직을 그대로 재사용할 수 있습니다.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

from ..models import Event

DEFAULT_DB_PATH = "team_schedule.db"
DEFAULT_TZ = "Asia/Seoul"


def resolve_db_path(path: str | None = None) -> str:
    """DB 파일 경로를 결정합니다(인자 > 환경변수 > 기본값)."""
    if path:
        return path
    return os.environ.get("TEAM_SCHEDULE_DB", DEFAULT_DB_PATH)


def _ensure_aware(dt: datetime, tz: str) -> datetime:
    """naive datetime 이면 주어진 시간대로 간주해 aware 로 만듭니다."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(tz))
    return dt


class ScheduleDB:
    """팀 일정을 담는 SQLite 저장소."""

    def __init__(self, path: str | None = None, tz: str = DEFAULT_TZ):
        self.path = resolve_db_path(path)
        self.tz = tz
        self.init_schema()

    # -- 연결 ---------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id          TEXT PRIMARY KEY,
                    summary     TEXT NOT NULL,
                    start       TEXT NOT NULL,
                    end         TEXT NOT NULL,
                    all_day     INTEGER NOT NULL DEFAULT 0,
                    location    TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    attendees   TEXT NOT NULL DEFAULT '[]',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS seen_events (
                    id      TEXT PRIMARY KEY,
                    updated TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind       TEXT NOT NULL,
                    message    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    # -- 행 <-> Event 변환 --------------------------------------------------
    def _row_to_event(self, row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"],
            summary=row["summary"],
            start=datetime.fromisoformat(row["start"]),
            end=datetime.fromisoformat(row["end"]),
            all_day=bool(row["all_day"]),
            attendees=json.loads(row["attendees"] or "[]"),
            location=row["location"] or "",
            description=row["description"] or "",
            updated=row["updated_at"] or "",
        )

    # -- 일정 CRUD ----------------------------------------------------------
    def list_events(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[Event]:
        """시작 시각 순으로 일정을 돌려줍니다.

        ``start``/``end`` 를 주면 그 구간과 겹치는 일정만(반열림 교차) 돌려줍니다.
        """
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY start ASC").fetchall()
        events = [self._row_to_event(r) for r in rows]
        if start is None and end is None:
            return events
        start_a = _ensure_aware(start, self.tz) if start else None
        end_a = _ensure_aware(end, self.tz) if end else None
        result = []
        for ev in events:
            ev_start = _ensure_aware(ev.start, self.tz)
            ev_end = _ensure_aware(ev.end, self.tz)
            if end_a is not None and ev_start >= end_a:
                continue
            if start_a is not None and ev_end <= start_a:
                continue
            result.append(ev)
        return result

    def get_event(self, event_id: str) -> Event | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._row_to_event(row) if row else None

    def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        *,
        all_day: bool = False,
        location: str = "",
        description: str = "",
        attendees: list[str] | None = None,
    ) -> Event:
        now = datetime.now(ZoneInfo(self.tz)).isoformat()
        event_id = uuid.uuid4().hex
        attendees = attendees or []
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO events
                    (id, summary, start, end, all_day, location,
                     description, attendees, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    summary,
                    _ensure_aware(start, self.tz).isoformat(),
                    _ensure_aware(end, self.tz).isoformat(),
                    1 if all_day else 0,
                    location,
                    description,
                    json.dumps(attendees, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        self.log_notification("create", f"일정 추가: {summary}")
        return self.get_event(event_id)  # type: ignore[return-value]

    def update_event(
        self,
        event_id: str,
        *,
        summary: str,
        start: datetime,
        end: datetime,
        all_day: bool = False,
        location: str = "",
        description: str = "",
        attendees: list[str] | None = None,
    ) -> Event | None:
        now = datetime.now(ZoneInfo(self.tz)).isoformat()
        attendees = attendees or []
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                """
                UPDATE events
                   SET summary = ?, start = ?, end = ?, all_day = ?,
                       location = ?, description = ?, attendees = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    summary,
                    _ensure_aware(start, self.tz).isoformat(),
                    _ensure_aware(end, self.tz).isoformat(),
                    1 if all_day else 0,
                    location,
                    description,
                    json.dumps(attendees, ensure_ascii=False),
                    now,
                    event_id,
                ),
            )
            if cur.rowcount == 0:
                return None
        self.log_notification("update", f"일정 수정: {summary}")
        return self.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        event = self.get_event(event_id)
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            deleted = cur.rowcount > 0
        if deleted and event is not None:
            self.log_notification("delete", f"일정 삭제: {event.summary}")
        return deleted

    # -- 알림 내역 ----------------------------------------------------------
    def log_notification(self, kind: str, message: str) -> None:
        now = datetime.now(ZoneInfo(self.tz)).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO notifications (kind, message, created_at) VALUES (?, ?, ?)",
                (kind, message, now),
            )

    def list_notifications(self, limit: int = 50) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT kind, message, created_at FROM notifications "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


class SqliteSeenStore:
    """기존 :class:`team_schedule.state.SeenState` 의 SQLite 버전.

    같은 인터페이스(``is_empty`` / ``diff`` / ``mark``)를 제공하므로
    워크플로우에서 JSON 상태 대신 그대로 끼워 쓸 수 있습니다. 여러 프로세스
    (cron 작업 + 웹 서버)가 하나의 DB 파일을 공유할 수 있다는 장점이 있습니다.
    """

    def __init__(self, path: str | None = None):
        self.path = resolve_db_path(path)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS seen_events "
                "(id TEXT PRIMARY KEY, updated TEXT NOT NULL DEFAULT '')"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def is_empty(self) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM seen_events").fetchone()
        return row["n"] == 0

    def diff(self, events: list[Event]) -> tuple[list[Event], list[Event]]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT id, updated FROM seen_events").fetchall()
        seen = {r["id"]: r["updated"] for r in rows}
        new_events: list[Event] = []
        updated_events: list[Event] = []
        for event in events:
            if event.id not in seen:
                new_events.append(event)
            elif seen[event.id] != event.updated:
                updated_events.append(event)
        return new_events, updated_events

    def mark(self, events: list[Event]) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                "INSERT INTO seen_events (id, updated) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated = excluded.updated",
                [(e.id, e.updated) for e in events],
            )
