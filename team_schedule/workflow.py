"""네 가지 흐름을 조율하는 워크플로우.

주입된 ``client`` (``list_events`` / ``create_recurring`` 을 가진 덕 타입) 를 받으므로
테스트에서는 가짜 클라이언트를 넘길 수 있습니다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .notify import format_conflicts, format_new_event
from .overlap import find_duplicates, find_overlaps
from .recurring import RecurringSpec
from .state import SeenState
from .summary import slack_daily, slack_weekly


def notify_new_events(
    client,
    config,
    notifier,
    *,
    prime_if_empty: bool = True,
    lookahead_days: int = 30,
) -> list:
    """다가오는 일정을 조회해 새 일정을 Slack 으로 알립니다.

    첫 실행(상태 비어 있음)이면 알림 없이 현재 일정만 기록(prime)합니다.
    """
    tzinfo = ZoneInfo(config.timezone)
    now = datetime.now(tzinfo)
    events = client.list_events(now, now + timedelta(days=lookahead_days))

    state = SeenState.load(config.state_file)
    if prime_if_empty and state.is_empty():
        state.mark(events)
        state.save(config.state_file)
        return []

    new_events, _updated = state.diff(events)
    for event in new_events:
        notifier.post(format_new_event(event, config.timezone))

    state.mark(events)
    state.save(config.state_file)
    return new_events


def post_daily_summary(client, config, notifier, day: date | None = None) -> str:
    """하루 일정 요약을 Slack 으로 보냅니다."""
    tzinfo = ZoneInfo(config.timezone)
    if day is None:
        day = datetime.now(tzinfo).date()
    start = datetime.combine(day, datetime.min.time(), tzinfo)
    end = start + timedelta(days=1)
    events = client.list_events(start, end)
    text = slack_daily(events, day, config.timezone)
    notifier.post(text)
    return text


def post_weekly_summary(client, config, notifier, week_start: date | None = None) -> str:
    """주간 일정 요약을 Slack 으로 보냅니다."""
    tzinfo = ZoneInfo(config.timezone)
    if week_start is None:
        today = datetime.now(tzinfo).date()
        week_start = today - timedelta(days=today.weekday())
    start = datetime.combine(week_start, datetime.min.time(), tzinfo)
    end = start + timedelta(days=7)
    events = client.list_events(start, end)
    text = slack_weekly(events, week_start, config.timezone)
    notifier.post(text)
    return text


def report_conflicts(client, config, notifier, *, window_days: int = 14):
    """기간 내 겹침/중복을 찾아 있을 때만 Slack 으로 보냅니다."""
    tzinfo = ZoneInfo(config.timezone)
    now = datetime.now(tzinfo)
    events = client.list_events(now, now + timedelta(days=window_days))
    overlaps = find_overlaps(events)
    duplicates = find_duplicates(events)
    if not overlaps and not duplicates:
        return None
    text = format_conflicts(overlaps, duplicates, config.timezone)
    notifier.post(text)
    return text


def add_recurring(client, spec: RecurringSpec) -> dict:
    """반복 일정을 생성합니다."""
    return client.create_recurring(spec)
