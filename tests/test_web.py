"""team_schedule.web 테스트 (FastAPI TestClient + SQLite, 네트워크/구글 없음)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from team_schedule.models import Event
from team_schedule.web.app import create_app
from team_schedule.web.db import ScheduleDB, SqliteSeenStore

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture()
def client(db_path):
    app = create_app(db_path=db_path)
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# ScheduleDB (SQLite 저장소)
# --------------------------------------------------------------------------- #
def test_db_create_get_update_delete(db_path):
    db = ScheduleDB(db_path)
    ev = db.create_event(
        "회의",
        datetime(2026, 1, 5, 9, tzinfo=KST),
        datetime(2026, 1, 5, 10, tzinfo=KST),
        location="회의실 A",
        attendees=["a@x.com", "b@x.com"],
    )
    assert ev.id
    assert isinstance(ev, Event)
    assert ev.summary == "회의"
    assert ev.attendees == ["a@x.com", "b@x.com"]

    fetched = db.get_event(ev.id)
    assert fetched is not None
    assert fetched.location == "회의실 A"

    updated = db.update_event(
        ev.id,
        summary="수정된 회의",
        start=datetime(2026, 1, 5, 11, tzinfo=KST),
        end=datetime(2026, 1, 5, 12, tzinfo=KST),
    )
    assert updated.summary == "수정된 회의"
    assert db.get_event(ev.id).summary == "수정된 회의"

    assert db.delete_event(ev.id) is True
    assert db.get_event(ev.id) is None
    assert db.delete_event(ev.id) is False


def test_db_list_filter_by_date(db_path):
    db = ScheduleDB(db_path)
    db.create_event("1월", datetime(2026, 1, 5, 9, tzinfo=KST), datetime(2026, 1, 5, 10, tzinfo=KST))
    db.create_event("2월", datetime(2026, 2, 5, 9, tzinfo=KST), datetime(2026, 2, 5, 10, tzinfo=KST))

    all_ev = db.list_events()
    assert len(all_ev) == 2

    jan = db.list_events(
        datetime(2026, 1, 1, tzinfo=KST), datetime(2026, 1, 31, tzinfo=KST)
    )
    assert [e.summary for e in jan] == ["1월"]


def test_db_logs_notifications(db_path):
    db = ScheduleDB(db_path)
    db.create_event("a", datetime(2026, 1, 5, 9, tzinfo=KST), datetime(2026, 1, 5, 10, tzinfo=KST))
    items = db.list_notifications()
    assert items
    assert items[0]["kind"] == "create"
    assert "a" in items[0]["message"]


def test_sqlite_seen_store(db_path):
    store = SqliteSeenStore(db_path)
    e1 = Event("1", "A", datetime(2026, 1, 5, 9, tzinfo=KST), datetime(2026, 1, 5, 10, tzinfo=KST), updated="u1")
    assert store.is_empty()
    new, updated = store.diff([e1])
    assert {e.id for e in new} == {"1"}
    store.mark([e1])
    assert not store.is_empty()

    e1b = Event("1", "A", e1.start, e1.end, updated="u2")
    e2 = Event("2", "B", e1.start, e1.end, updated="u1")
    new, updated = store.diff([e1b, e2])
    assert {e.id for e in new} == {"2"}
    assert {e.id for e in updated} == {"1"}


# --------------------------------------------------------------------------- #
# 웹 라우트
# --------------------------------------------------------------------------- #
def test_dashboard_ok(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "대시보드" in r.text


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_empty_list_ok(client):
    r = client.get("/events")
    assert r.status_code == 200
    assert "표시할 일정이 없습니다" in r.text


def test_create_edit_delete_flow(client):
    # 생성 폼
    assert client.get("/events/new").status_code == 200

    # 생성 (TestClient 는 리다이렉트를 따라감 → 최종 목록 200)
    r = client.post(
        "/events",
        data={
            "summary": "킥오프",
            "start": "2026-01-05T09:00",
            "end": "2026-01-05T10:00",
            "location": "회의실 A",
            "attendees": "a@x.com, b@x.com",
            "description": "설명",
        },
    )
    assert r.status_code == 200
    assert "킥오프" in r.text

    # DB 에서 id 확인
    db = client.app.state.db
    events = db.list_events()
    assert len(events) == 1
    eid = events[0].id

    # 수정 폼에 기존 값
    rf = client.get(f"/events/{eid}/edit")
    assert rf.status_code == 200
    assert "킥오프" in rf.text

    # 수정
    r2 = client.post(
        f"/events/{eid}",
        data={
            "summary": "킥오프(수정)",
            "start": "2026-01-05T09:00",
            "end": "2026-01-05T11:00",
        },
    )
    assert r2.status_code == 200
    assert "킥오프(수정)" in r2.text
    assert db.get_event(eid).summary == "킥오프(수정)"

    # 삭제
    r3 = client.post(f"/events/{eid}/delete")
    assert r3.status_code == 200
    assert db.get_event(eid) is None


def test_create_validation_error(client):
    # 종료가 시작보다 앞 → 400 과 에러 메시지, 저장 안 됨
    r = client.post(
        "/events",
        data={"summary": "x", "start": "2026-01-05T10:00", "end": "2026-01-05T09:00"},
    )
    assert r.status_code == 400
    assert "종료 시각" in r.text
    assert client.app.state.db.list_events() == []


def test_conflict_shown_in_list(client):
    db = client.app.state.db
    db.create_event("회의", datetime(2026, 3, 2, 9, tzinfo=KST), datetime(2026, 3, 2, 11, tzinfo=KST))
    db.create_event("회의", datetime(2026, 3, 2, 10, tzinfo=KST), datetime(2026, 3, 2, 12, tzinfo=KST))
    r = client.get("/events")
    assert r.status_code == 200
    assert "충돌" in r.text


def test_edit_missing_returns_404(client):
    assert client.get("/events/does-not-exist/edit").status_code == 404


def test_notifications_page(client):
    client.post(
        "/events",
        data={"summary": "알림테스트", "start": "2026-01-05T09:00", "end": "2026-01-05T10:00"},
    )
    r = client.get("/notifications")
    assert r.status_code == 200
    assert "알림테스트" in r.text


def test_date_filter_on_list(client):
    db = client.app.state.db
    db.create_event("1월", datetime(2026, 1, 5, 9, tzinfo=KST), datetime(2026, 1, 5, 10, tzinfo=KST))
    db.create_event("2월", datetime(2026, 2, 5, 9, tzinfo=KST), datetime(2026, 2, 5, 10, tzinfo=KST))
    r = client.get("/events", params={"start": "2026-01-01", "end": "2026-01-31"})
    assert r.status_code == 200
    assert "1월" in r.text
    assert "2월" not in r.text
