"""team_schedule 테스트 (순수 표준 라이브러리, 구글 import 없음, 네트워크 없음)."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from team_schedule import (
    Config,
    Event,
    SeenState,
    SlackNotifier,
    RecurringSpec,
    build_rrule,
    daily_summary,
    find_duplicates,
    find_overlaps,
    weekly_summary,
)
from team_schedule.notify import format_conflicts, format_new_event
from team_schedule.recurring import Weekday
from team_schedule.summary import slack_daily
from team_schedule import workflow

KST = ZoneInfo("Asia/Seoul")


def _dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=KST)


def make_event(eid, summary, start, end, **kw):
    return Event(id=eid, summary=summary, start=start, end=end, **kw)


# --------------------------------------------------------------------------- #
# Event.from_google
# --------------------------------------------------------------------------- #
def test_from_google_timed():
    resource = {
        "id": "abc",
        "summary": "주간 회의",
        "start": {"dateTime": "2026-01-05T09:00:00+09:00"},
        "end": {"dateTime": "2026-01-05T10:00:00+09:00"},
        "attendees": [{"email": "a@x.com"}, {"email": "b@x.com"}, {"foo": "no-email"}],
        "organizer": {"email": "boss@x.com"},
        "location": "회의실 A",
        "description": "설명",
        "htmlLink": "https://cal/abc",
        "updated": "2026-01-01T00:00:00Z",
    }
    event = Event.from_google(resource)
    assert event.id == "abc"
    assert event.summary == "주간 회의"
    assert event.all_day is False
    assert event.attendees == ["a@x.com", "b@x.com"]
    assert event.organizer == "boss@x.com"
    assert event.location == "회의실 A"
    assert event.html_link == "https://cal/abc"
    assert event.duration() == timedelta(hours=1)


def test_from_google_timed_z_suffix():
    resource = {
        "id": "z1",
        "summary": "UTC 회의",
        "start": {"dateTime": "2026-01-05T00:00:00Z"},
        "end": {"dateTime": "2026-01-05T01:00:00Z"},
    }
    event = Event.from_google(resource)
    assert event.start == datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    assert event.all_day is False


def test_from_google_all_day_and_default_summary():
    resource = {
        "id": "day1",
        "start": {"date": "2026-01-05"},
        "end": {"date": "2026-01-06"},  # 구글 종일 종료일은 배타적 → 그대로 유지
    }
    event = Event.from_google(resource)
    assert event.all_day is True
    assert event.summary == "(제목 없음)"
    assert event.start == datetime(2026, 1, 5, 0, 0, tzinfo=KST)
    assert event.end == datetime(2026, 1, 6, 0, 0, tzinfo=KST)
    assert event.attendees == []


# --------------------------------------------------------------------------- #
# Event.overlaps
# --------------------------------------------------------------------------- #
def test_overlaps_touching_endpoints_do_not_overlap():
    a = make_event("1", "A", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10))
    b = make_event("2", "B", _dt(2026, 1, 5, 10), _dt(2026, 1, 5, 11))
    assert a.overlaps(b) is False
    assert b.overlaps(a) is False


def test_overlaps_nested():
    outer = make_event("1", "A", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 12))
    inner = make_event("2", "B", _dt(2026, 1, 5, 10), _dt(2026, 1, 5, 11))
    assert outer.overlaps(inner) is True
    assert inner.overlaps(outer) is True


def test_overlaps_disjoint():
    a = make_event("1", "A", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10))
    b = make_event("2", "B", _dt(2026, 1, 5, 11), _dt(2026, 1, 5, 12))
    assert a.overlaps(b) is False


def test_overlaps_partial():
    a = make_event("1", "A", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 11))
    b = make_event("2", "B", _dt(2026, 1, 5, 10), _dt(2026, 1, 5, 12))
    assert a.overlaps(b) is True


# --------------------------------------------------------------------------- #
# find_overlaps / find_duplicates
# --------------------------------------------------------------------------- #
def test_find_overlaps():
    a = make_event("1", "A", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 11))
    b = make_event("2", "B", _dt(2026, 1, 5, 10), _dt(2026, 1, 5, 12))
    c = make_event("3", "C", _dt(2026, 1, 5, 13), _dt(2026, 1, 5, 14))
    pairs = find_overlaps([c, b, a])
    assert len(pairs) == 1
    assert {pairs[0][0].id, pairs[0][1].id} == {"1", "2"}


def test_find_duplicates():
    a = make_event("1", " Daily  Standup ", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10))
    b = make_event("2", "daily standup", _dt(2026, 1, 5, 9, 30), _dt(2026, 1, 5, 10, 30))
    c = make_event("3", "다른 회의", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10))
    groups = find_duplicates([a, b, c])
    assert len(groups) == 1
    assert {e.id for e in groups[0]} == {"1", "2"}


def test_find_duplicates_same_title_no_overlap_not_grouped():
    a = make_event("1", "회의", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10))
    b = make_event("2", "회의", _dt(2026, 1, 6, 9), _dt(2026, 1, 6, 10))
    assert find_duplicates([a, b]) == []


# --------------------------------------------------------------------------- #
# build_rrule
# --------------------------------------------------------------------------- #
def test_build_rrule_weekly_byday_count():
    rrule = build_rrule("WEEKLY", interval=1, count=10, byday=[Weekday.MO, Weekday.WE, Weekday.FR])
    assert rrule == "RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,WE,FR;COUNT=10"


def test_build_rrule_daily():
    assert build_rrule("daily") == "RRULE:FREQ=DAILY;INTERVAL=1"


def test_build_rrule_byday_strings():
    rrule = build_rrule("WEEKLY", byday=["mo", "fr"])
    assert "BYDAY=MO,FR" in rrule


def test_build_rrule_until_utc_format():
    until = datetime(2026, 3, 1, 12, 0, tzinfo=KST)  # 09:00 == 03:00 UTC
    rrule = build_rrule("WEEKLY", until=until)
    assert rrule.endswith("UNTIL=20260301T030000Z")


def test_build_rrule_invalid_freq():
    with pytest.raises(ValueError):
        build_rrule("HOURLY")


def test_build_rrule_count_and_until_both():
    with pytest.raises(ValueError):
        build_rrule("DAILY", count=5, until=datetime(2026, 1, 1, tzinfo=timezone.utc))


# --------------------------------------------------------------------------- #
# RecurringSpec
# --------------------------------------------------------------------------- #
def test_recurring_spec_to_google_body():
    spec = RecurringSpec.weekly(
        "스탠드업",
        _dt(2026, 1, 5, 9),
        _dt(2026, 1, 5, 9, 30),
        days=[Weekday.MO, Weekday.WE],
        count=4,
        attendees=["a@x.com"],
        location="회의실",
    )
    body = spec.to_google_body()
    assert body["summary"] == "스탠드업"
    assert body["location"] == "회의실"
    assert body["start"]["timeZone"] == "Asia/Seoul"
    assert body["start"]["dateTime"].startswith("2026-01-05T09:00:00")
    assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,WE;COUNT=4"]
    assert body["attendees"] == [{"email": "a@x.com"}]


def test_recurring_spec_daily_constructor():
    spec = RecurringSpec.daily("체조", _dt(2026, 1, 5, 8), _dt(2026, 1, 5, 8, 10), count=3)
    assert spec.rrule == "RRULE:FREQ=DAILY;INTERVAL=1;COUNT=3"


# --------------------------------------------------------------------------- #
# summaries
# --------------------------------------------------------------------------- #
def test_daily_summary_no_events():
    text = daily_summary([], date(2026, 1, 5), boxed=False)
    assert "일정이 없습니다" in text
    assert "2026-01-05" in text


def test_daily_summary_with_events_boxed():
    events = [
        make_event("1", "아침 회의", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10), attendees=["a@x.com", "b@x.com"]),
        make_event("2", "휴가", _dt(2026, 1, 5, 0), _dt(2026, 1, 6, 0), all_day=True),
    ]
    text = daily_summary(events, date(2026, 1, 5))
    assert "아침 회의" in text
    assert "09:00–10:00" in text
    assert "2명" in text
    assert "종일" in text
    # 상자 테두리가 둘러져 있어야 함
    assert "┌" in text and "┘" in text


def test_weekly_summary():
    monday = date(2026, 1, 5)  # 월요일
    events = [make_event("1", "회의", _dt(2026, 1, 7, 14), _dt(2026, 1, 7, 15))]
    text = weekly_summary(events, monday)
    assert "주간 일정" in text
    assert "회의" in text
    assert "01-07 (수)" in text
    assert "일정 없음" in text  # 다른 요일


def test_slack_daily_is_mrkdwn_without_box():
    events = [make_event("1", "회의", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10))]
    text = slack_daily(events, date(2026, 1, 5))
    assert text.startswith("*")
    assert "┌" not in text


# --------------------------------------------------------------------------- #
# SeenState
# --------------------------------------------------------------------------- #
def test_seen_state_diff_and_persistence(tmp_path):
    path = tmp_path / "state.json"
    e1 = make_event("1", "A", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10), updated="u1")
    e2 = make_event("2", "B", _dt(2026, 1, 5, 11), _dt(2026, 1, 5, 12), updated="u1")

    state = SeenState.load(path)
    assert state.is_empty()
    new, updated = state.diff([e1, e2])
    assert {e.id for e in new} == {"1", "2"}
    assert updated == []

    state.mark([e1, e2])
    state.save(path)

    # 다시 로드: e1 그대로, e2 변경, e3 신규
    reloaded = SeenState.load(path)
    e2_changed = make_event("2", "B", _dt(2026, 1, 5, 11), _dt(2026, 1, 5, 12), updated="u2")
    e3 = make_event("3", "C", _dt(2026, 1, 5, 13), _dt(2026, 1, 5, 14), updated="u1")
    new, updated = reloaded.diff([e1, e2_changed, e3])
    assert {e.id for e in new} == {"3"}
    assert {e.id for e in updated} == {"2"}


def test_seen_state_prime(tmp_path):
    path = tmp_path / "state.json"
    events = [make_event("1", "A", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10), updated="u1")]
    SeenState.prime(events, path)
    reloaded = SeenState.load(path)
    new, updated = reloaded.diff(events)
    assert new == [] and updated == []


# --------------------------------------------------------------------------- #
# SlackNotifier / formatters
# --------------------------------------------------------------------------- #
def test_slack_notifier_dry_run_captures_payload():
    notifier = SlackNotifier("https://example", dry_run=True)
    payload = notifier.post("안녕")
    assert payload == {"text": "안녕"}
    assert notifier.sent == [{"text": "안녕"}]


def test_format_new_event_substrings():
    event = make_event(
        "1", "킥오프", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 10),
        attendees=["a@x.com"], location="회의실 A", html_link="https://cal/1",
    )
    text = format_new_event(event)
    assert "🆕" in text
    assert "킥오프" in text
    assert "09:00" in text
    assert "회의실 A" in text
    assert "https://cal/1" in text


def test_format_conflicts_empty_safe():
    assert "없습니다" in format_conflicts([], [])


def test_format_conflicts_content():
    a = make_event("1", "회의", _dt(2026, 1, 5, 9), _dt(2026, 1, 5, 11))
    b = make_event("2", "회의", _dt(2026, 1, 5, 10), _dt(2026, 1, 5, 12))
    text = format_conflicts([(a, b)], [[a, b]])
    assert "겹치는 일정" in text
    assert "중복 일정" in text


# --------------------------------------------------------------------------- #
# workflow with a fake client
# --------------------------------------------------------------------------- #
class FakeCalendarClient:
    def __init__(self, events=None):
        self._events = events or []
        self.created = []

    def list_events(self, time_min, time_max, max_results=250):
        return list(self._events)

    def create_recurring(self, spec):
        body = spec.to_google_body()
        self.created.append(body)
        return {"id": "created-1", **body}


def _config(tmp_path):
    return Config(
        calendar_id="cal",
        service_account_file="sa.json",
        slack_webhook_url="https://example",
        state_file=str(tmp_path / "state.json"),
        timezone="Asia/Seoul",
    )


def test_notify_new_events_first_run_primes(tmp_path):
    now = datetime.now(KST)
    events = [make_event("1", "A", now + timedelta(days=1), now + timedelta(days=1, hours=1), updated="u1")]
    client = FakeCalendarClient(events)
    notifier = SlackNotifier("https://example", dry_run=True)
    config = _config(tmp_path)

    posted = workflow.notify_new_events(client, config, notifier)
    assert posted == []
    assert notifier.sent == []  # 첫 실행은 알림 없이 prime
    # 상태가 기록됐으므로 두 번째 실행에서도 새 일정 없음
    posted2 = workflow.notify_new_events(client, config, notifier)
    assert posted2 == []
    assert notifier.sent == []


def test_notify_new_events_posts_new(tmp_path):
    now = datetime.now(KST)
    e1 = make_event("1", "A", now + timedelta(days=1), now + timedelta(days=1, hours=1), updated="u1")
    client = FakeCalendarClient([e1])
    notifier = SlackNotifier("https://example", dry_run=True)
    config = _config(tmp_path)

    # prime
    workflow.notify_new_events(client, config, notifier)
    assert notifier.sent == []

    # 새 일정 추가 → 알림 발생
    e2 = make_event("2", "B", now + timedelta(days=2), now + timedelta(days=2, hours=1), updated="u1")
    client._events.append(e2)
    posted = workflow.notify_new_events(client, config, notifier)
    assert {e.id for e in posted} == {"2"}
    assert len(notifier.sent) == 1
    assert "B" in notifier.sent[0]["text"]


def test_report_conflicts(tmp_path):
    now = datetime.now(KST)
    a = make_event("1", "회의", now + timedelta(hours=1), now + timedelta(hours=3))
    b = make_event("2", "회의", now + timedelta(hours=2), now + timedelta(hours=4))
    client = FakeCalendarClient([a, b])
    notifier = SlackNotifier("https://example", dry_run=True)
    config = _config(tmp_path)

    result = workflow.report_conflicts(client, config, notifier)
    assert result is not None
    assert len(notifier.sent) == 1
    assert "겹치는 일정" in notifier.sent[0]["text"]


def test_report_conflicts_none(tmp_path):
    now = datetime.now(KST)
    a = make_event("1", "회의", now + timedelta(hours=1), now + timedelta(hours=2))
    b = make_event("2", "점심", now + timedelta(hours=3), now + timedelta(hours=4))
    client = FakeCalendarClient([a, b])
    notifier = SlackNotifier("https://example", dry_run=True)
    config = _config(tmp_path)
    assert workflow.report_conflicts(client, config, notifier) is None
    assert notifier.sent == []


def test_add_recurring_uses_spec_body(tmp_path):
    client = FakeCalendarClient()
    spec = RecurringSpec.daily("체조", _dt(2026, 1, 5, 8), _dt(2026, 1, 5, 8, 10), count=3)
    created = workflow.add_recurring(client, spec)
    assert created["id"] == "created-1"
    assert client.created[0]["recurrence"] == ["RRULE:FREQ=DAILY;INTERVAL=1;COUNT=3"]


def test_config_validate_missing():
    config = Config()
    with pytest.raises(ValueError) as exc:
        config.validate()
    msg = str(exc.value)
    assert "GOOGLE_CALENDAR_ID" in msg
    assert "SLACK_WEBHOOK_URL" in msg


def test_config_from_env():
    env = {
        "GOOGLE_CALENDAR_ID": "cal",
        "GOOGLE_SERVICE_ACCOUNT_FILE": "sa.json",
        "SLACK_WEBHOOK_URL": "https://hook",
    }
    config = Config.from_env(env)
    assert config.calendar_id == "cal"
    assert config.timezone == "Asia/Seoul"  # 기본값
    config.validate()  # 예외 없어야 함
