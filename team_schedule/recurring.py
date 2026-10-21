"""반복 일정(RRULE) 생성 (순수 표준 라이브러리)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


class Weekday(enum.Enum):
    """RRULE BYDAY 토큰."""

    MO = "MO"
    TU = "TU"
    WE = "WE"
    TH = "TH"
    FR = "FR"
    SA = "SA"
    SU = "SU"


_VALID_FREQ = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")


def build_rrule(
    freq: str,
    interval: int = 1,
    count: int | None = None,
    until: datetime | None = None,
    byday: list | None = None,
) -> str:
    """RFC5545 RRULE 문자열을 만듭니다.

    예: ``RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,WE,FR;COUNT=10``

    - ``freq`` 는 DAILY/WEEKLY/MONTHLY/YEARLY 중 하나여야 합니다.
    - ``until`` 은 datetime 이며 ``UNTIL=YYYYMMDDTHHMMSSZ`` (UTC) 로 포맷됩니다.
    - ``byday`` 는 :class:`Weekday` 혹은 문자열의 리스트.
    - ``count`` 와 ``until`` 은 동시에 지정할 수 없습니다.
    """
    freq_upper = freq.upper()
    if freq_upper not in _VALID_FREQ:
        raise ValueError(f"freq 는 {_VALID_FREQ} 중 하나여야 합니다: {freq!r}")
    if count is not None and until is not None:
        raise ValueError("count 와 until 은 동시에 지정할 수 없습니다")

    parts = [f"FREQ={freq_upper}", f"INTERVAL={interval}"]

    if byday:
        tokens = []
        for day in byday:
            if isinstance(day, Weekday):
                tokens.append(day.value)
            else:
                tokens.append(str(day).upper())
        parts.append("BYDAY=" + ",".join(tokens))

    if count is not None:
        parts.append(f"COUNT={count}")

    if until is not None:
        if until.tzinfo is not None:
            until = until.astimezone(timezone.utc)
        parts.append("UNTIL=" + until.strftime("%Y%m%dT%H%M%SZ"))

    return "RRULE:" + ";".join(parts)


@dataclass
class RecurringSpec:
    """반복 일정 명세. 구글 캘린더 insert 바디로 변환할 수 있습니다."""

    summary: str
    start: datetime
    end: datetime
    rrule: str
    attendees: list[str] = field(default_factory=list)
    location: str = ""
    description: str = ""
    timezone: str = "Asia/Seoul"

    def to_google_body(self) -> dict:
        """구글 캘린더 events().insert 바디를 생성합니다."""
        return {
            "summary": self.summary,
            "location": self.location,
            "description": self.description,
            "start": {"dateTime": self.start.isoformat(), "timeZone": self.timezone},
            "end": {"dateTime": self.end.isoformat(), "timeZone": self.timezone},
            "recurrence": [self.rrule],
            "attendees": [{"email": email} for email in self.attendees],
        }

    @classmethod
    def weekly(
        cls,
        summary: str,
        start: datetime,
        end: datetime,
        days: list,
        count: int | None = None,
        until: datetime | None = None,
        interval: int = 1,
        **kw,
    ) -> "RecurringSpec":
        """주간 반복 명세를 만듭니다."""
        rrule = build_rrule("WEEKLY", interval=interval, count=count, until=until, byday=days)
        return cls(summary=summary, start=start, end=end, rrule=rrule, **kw)

    @classmethod
    def daily(
        cls,
        summary: str,
        start: datetime,
        end: datetime,
        count: int | None = None,
        until: datetime | None = None,
        interval: int = 1,
        **kw,
    ) -> "RecurringSpec":
        """일간 반복 명세를 만듭니다."""
        rrule = build_rrule("DAILY", interval=interval, count=count, until=until)
        return cls(summary=summary, start=start, end=end, rrule=rrule, **kw)
