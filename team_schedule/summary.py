"""일정 요약 문자열 생성 (순수 표준 라이브러리 + ins_box.box 재사용)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ins_box import box

from .models import Event

_KO_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def _as_tz(dt: datetime, tzinfo: ZoneInfo) -> datetime:
    """aware 면 변환, naive 면 해당 tz 로 간주."""
    if dt.tzinfo is not None:
        return dt.astimezone(tzinfo)
    return dt.replace(tzinfo=tzinfo)


def _occurs_on(event: Event, day: date, tzinfo: ZoneInfo) -> bool:
    """일정이 주어진 날짜 구간과 겹치는지 (반열림)."""
    day_start = datetime.combine(day, datetime.min.time(), tzinfo)
    day_end = day_start + timedelta(days=1)
    start = _as_tz(event.start, tzinfo)
    end = _as_tz(event.end, tzinfo)
    return start < day_end and day_start < end


def _format_event_line(event: Event, tzinfo: ZoneInfo) -> str:
    if event.all_day:
        time_part = "종일"
    else:
        start = _as_tz(event.start, tzinfo)
        end = _as_tz(event.end, tzinfo)
        time_part = f"{start:%H:%M}–{end:%H:%M}"
    line = f"{time_part}  {event.summary}"
    if event.attendees:
        line += f"  · {len(event.attendees)}명"
    return line


def _events_on(events: list[Event], day: date, tzinfo: ZoneInfo) -> list[Event]:
    return sorted(
        (e for e in events if _occurs_on(e, day, tzinfo)),
        key=lambda e: e.start,
    )


def daily_summary(events: list[Event], day: date, tz: str = "Asia/Seoul", boxed: bool = True) -> str:
    """하루 일정 요약. ``boxed`` 면 ins_box.box 로 감쌉니다."""
    tzinfo = ZoneInfo(tz)
    weekday = _KO_WEEKDAYS[day.weekday()]
    header = f"📅 {day:%Y-%m-%d} ({weekday}) 일정"
    day_events = _events_on(events, day, tzinfo)
    if not day_events:
        body = f"{header}\n일정이 없습니다"
    else:
        body = "\n".join([header] + [_format_event_line(e, tzinfo) for e in day_events])
    return box(body) if boxed else body


def weekly_summary(events: list[Event], week_start: date, tz: str = "Asia/Seoul") -> str:
    """week_start 부터 7일간 일정을 요일별로 묶어 요약."""
    tzinfo = ZoneInfo(tz)
    lines = [f"🗓 {week_start:%Y-%m-%d} 주간 일정"]
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        weekday = _KO_WEEKDAYS[day.weekday()]
        lines.append(f"{day:%m-%d} ({weekday})")
        day_events = _events_on(events, day, tzinfo)
        if not day_events:
            lines.append("  일정 없음")
        else:
            lines.extend("  " + _format_event_line(e, tzinfo) for e in day_events)
    return "\n".join(lines)


def slack_daily(events: list[Event], day: date, tz: str = "Asia/Seoul") -> str:
    """하루 일정을 Slack mrkdwn 으로 (상자 없음)."""
    tzinfo = ZoneInfo(tz)
    weekday = _KO_WEEKDAYS[day.weekday()]
    header = f"*📅 {day:%Y-%m-%d} ({weekday}) 일정*"
    day_events = _events_on(events, day, tzinfo)
    if not day_events:
        return f"{header}\n일정이 없습니다"
    return "\n".join([header] + [_format_event_line(e, tzinfo) for e in day_events])


def slack_weekly(events: list[Event], week_start: date, tz: str = "Asia/Seoul") -> str:
    """주간 일정을 Slack mrkdwn 으로 (상자 없음)."""
    tzinfo = ZoneInfo(tz)
    lines = [f"*🗓 {week_start:%Y-%m-%d} 주간 일정*"]
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        weekday = _KO_WEEKDAYS[day.weekday()]
        lines.append(f"*{day:%m-%d} ({weekday})*")
        day_events = _events_on(events, day, tzinfo)
        if not day_events:
            lines.append("  일정 없음")
        else:
            lines.extend("  " + _format_event_line(e, tzinfo) for e in day_events)
    return "\n".join(lines)
