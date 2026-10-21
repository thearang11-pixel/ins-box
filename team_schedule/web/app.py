"""FastAPI 웹 앱 (서버 렌더링, Jinja2).

빌드 단계가 전혀 없는 순수 서버 렌더링 HTML 로, 구글 자격 증명 없이
SQLite DB 만으로 동작합니다. 기존 도메인 로직을 재사용합니다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..overlap import find_duplicates, find_overlaps
from ..summary import daily_summary, weekly_summary
from .db import DEFAULT_TZ, ScheduleDB, resolve_db_path

_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"

_KO_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def _parse_dt(value: str, tz: str) -> datetime:
    """datetime-local/date 문자열을 해당 시간대의 aware datetime 으로."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt


def _parse_attendees(raw: str) -> list[str]:
    return [a.strip() for a in raw.split(",") if a.strip()]


def _conflict_ids(events) -> set[str]:
    """겹침/중복에 연루된 일정 id 집합을 돌려줍니다."""
    ids: set[str] = set()
    for a, b in find_overlaps(events):
        ids.add(a.id)
        ids.add(b.id)
    for group in find_duplicates(events):
        ids.update(e.id for e in group)
    return ids


def create_app(db_path: str | None = None, tz: str = DEFAULT_TZ) -> FastAPI:
    """앱 팩토리. 테스트에서는 임시 DB 경로를 넘길 수 있습니다."""
    app = FastAPI(title="팀 일정 관리", docs_url=None, redoc_url=None)
    app.state.db = ScheduleDB(resolve_db_path(db_path), tz=tz)
    app.state.tz = tz

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    templates.env.filters["dt"] = _jinja_dt_filter(tz)
    templates.env.filters["dtlocal"] = _jinja_dtlocal_filter(tz)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    def db() -> ScheduleDB:
        return app.state.db

    # -- 대시보드 -----------------------------------------------------------
    @app.get("/")
    def dashboard(request: Request):
        tzinfo = ZoneInfo(tz)
        today = datetime.now(tzinfo).date()
        week_start = today - timedelta(days=today.weekday())
        all_events = db().list_events()
        upcoming = [
            e for e in all_events
            if _as_aware(e.end, tz) >= datetime.now(tzinfo)
        ]
        conflict_ids = _conflict_ids(all_events)
        daily_text = daily_summary(all_events, today, tz=tz, boxed=True)
        weekly_text = weekly_summary(all_events, week_start, tz=tz)
        return templates.TemplateResponse(
                request,
                "dashboard.html",
                {
                "active": "dashboard",
                "today": today,
                "weekday": _KO_WEEKDAYS[today.weekday()],
                "total": len(all_events),
                "upcoming": len(upcoming),
                "conflicts": len(conflict_ids),
                "daily_text": daily_text,
                "weekly_text": weekly_text,
            },
        )

    # -- 일정 목록 ----------------------------------------------------------
    @app.get("/events")
    def event_list(request: Request, start: str | None = None, end: str | None = None):
        start_dt = _parse_dt(start, tz) if start else None
        # 끝 날짜는 '그 날 포함'이 자연스러우므로 하루를 더해 반열림 처리
        end_dt = _parse_dt(end, tz) + timedelta(days=1) if end else None
        events = db().list_events(start_dt, end_dt)
        conflict_ids = _conflict_ids(events)
        return templates.TemplateResponse(
                request,
                "list.html",
                {
                "active": "events",
                "events": events,
                "conflict_ids": conflict_ids,
                "start": start or "",
                "end": end or "",
            },
        )

    # -- 추가 폼 / 처리 -----------------------------------------------------
    @app.get("/events/new")
    def new_event_form(request: Request):
        return templates.TemplateResponse(
                request,
                "form.html",
                { "active": "events", "event": None, "error": None},
        )

    @app.post("/events")
    def create_event(
        request: Request,
        summary: str = Form(...),
        start: str = Form(...),
        end: str = Form(...),
        all_day: str | None = Form(None),
        location: str = Form(""),
        description: str = Form(""),
        attendees: str = Form(""),
    ):
        error = _validate(summary, start, end, tz)
        if error:
            return templates.TemplateResponse(
                request,
                "form.html",
                {
                    "active": "events",
                    "event": _draft(summary, start, end, all_day, location, description, attendees),
                    "error": error,
                },
                status_code=400,
            )
        db().create_event(
            summary=summary.strip(),
            start=_parse_dt(start, tz),
            end=_parse_dt(end, tz),
            all_day=bool(all_day),
            location=location.strip(),
            description=description.strip(),
            attendees=_parse_attendees(attendees),
        )
        return RedirectResponse("/events", status_code=303)

    # -- 수정 폼 / 처리 -----------------------------------------------------
    @app.get("/events/{event_id}/edit")
    def edit_event_form(request: Request, event_id: str):
        event = db().get_event(event_id)
        if event is None:
            return _not_found(templates, request)
        return templates.TemplateResponse(
                request,
                "form.html",
                { "active": "events", "event": event, "error": None},
        )

    @app.post("/events/{event_id}")
    def update_event(
        request: Request,
        event_id: str,
        summary: str = Form(...),
        start: str = Form(...),
        end: str = Form(...),
        all_day: str | None = Form(None),
        location: str = Form(""),
        description: str = Form(""),
        attendees: str = Form(""),
    ):
        if db().get_event(event_id) is None:
            return _not_found(templates, request)
        error = _validate(summary, start, end, tz)
        if error:
            draft = _draft(summary, start, end, all_day, location, description, attendees)
            draft.id = event_id
            return templates.TemplateResponse(
                request,
                "form.html",
                { "active": "events", "event": draft, "error": error},
                status_code=400,
            )
        db().update_event(
            event_id,
            summary=summary.strip(),
            start=_parse_dt(start, tz),
            end=_parse_dt(end, tz),
            all_day=bool(all_day),
            location=location.strip(),
            description=description.strip(),
            attendees=_parse_attendees(attendees),
        )
        return RedirectResponse("/events", status_code=303)

    @app.post("/events/{event_id}/delete")
    def delete_event(event_id: str):
        db().delete_event(event_id)
        return RedirectResponse("/events", status_code=303)

    # -- 최근 알림 내역 -----------------------------------------------------
    @app.get("/notifications")
    def notifications(request: Request):
        return templates.TemplateResponse(
                request,
                "notifications.html",
                {
                "active": "notifications",
                "items": db().list_notifications(100),
            },
        )

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


# --------------------------------------------------------------------------- #
# 헬퍼
# --------------------------------------------------------------------------- #
def _as_aware(dt: datetime, tz: str) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo(tz))


def _validate(summary: str, start: str, end: str, tz: str) -> str | None:
    if not summary.strip():
        return "일정 제목을 입력해 주세요."
    try:
        s = _parse_dt(start, tz)
        e = _parse_dt(end, tz)
    except ValueError:
        return "시작/종료 시각 형식이 올바르지 않습니다."
    if e <= s:
        return "종료 시각은 시작 시각보다 뒤여야 합니다."
    return None


class _Draft:
    """폼 재렌더링용 임시 객체 (Event 와 동일한 속성 이름)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _draft(summary, start, end, all_day, location, description, attendees) -> _Draft:
    return _Draft(
        id="",
        summary=summary,
        start=start,
        end=end,
        all_day=bool(all_day),
        location=location,
        description=description,
        attendees=_parse_attendees(attendees),
    )


def _not_found(templates: Jinja2Templates, request: Request):
    return templates.TemplateResponse(
                request,
                "not_found.html",
                { "active": "events"},
        status_code=404,
    )


def _jinja_dt_filter(tz: str):
    """datetime 또는 ISO 문자열을 '2026-01-05 (월) 09:00' 로 포맷."""

    def _fmt(value, with_time: bool = True) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        if isinstance(value, datetime):
            value = _as_aware(value, tz).astimezone(ZoneInfo(tz))
            weekday = _KO_WEEKDAYS[value.weekday()]
            if with_time:
                return f"{value:%Y-%m-%d} ({weekday}) {value:%H:%M}"
            return f"{value:%Y-%m-%d} ({weekday})"
        if isinstance(value, date):
            weekday = _KO_WEEKDAYS[value.weekday()]
            return f"{value:%Y-%m-%d} ({weekday})"
        return str(value)

    return _fmt


def _jinja_dtlocal_filter(tz: str):
    """datetime/ISO 문자열을 ``<input type=datetime-local>`` 값으로 포맷."""

    def _fmt(value) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, datetime):
            value = _as_aware(value, tz).astimezone(ZoneInfo(tz))
            return f"{value:%Y-%m-%dT%H:%M}"
        # 폼 재렌더링 시 넘어온 원본 문자열은 그대로 사용
        return str(value)[:16]

    return _fmt


# uvicorn team_schedule.web.app:app 용 모듈 수준 인스턴스
app = create_app()
