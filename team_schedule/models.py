"""순수 표준 라이브러리로 구현한 일정 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass
class Event:
    """달력 일정 하나를 나타내는 값 객체."""

    id: str
    summary: str
    start: datetime
    end: datetime
    all_day: bool = False
    attendees: list[str] = field(default_factory=list)
    location: str = ""
    description: str = ""
    organizer: str = ""
    html_link: str = ""
    updated: str = ""

    def duration(self) -> timedelta:
        """일정 길이를 돌려줍니다."""
        return self.end - self.start

    def overlaps(self, other: "Event") -> bool:
        """두 일정의 시간 구간이 겹치면 True.

        구간은 반열림 ``[start, end)`` 으로 보며, 끝점이 맞닿은 경우는
        겹치지 않는 것으로 처리합니다.
        """
        return self.start < other.end and other.start < self.end

    @classmethod
    def from_google(cls, resource: dict, default_tz: str = "Asia/Seoul") -> "Event":
        """구글 캘린더 API 이벤트 리소스를 :class:`Event` 로 파싱합니다."""
        tz = ZoneInfo(default_tz)
        start_raw = resource.get("start", {}) or {}
        end_raw = resource.get("end", {}) or {}

        all_day = "dateTime" not in start_raw and "date" in start_raw
        if all_day:
            # 구글의 종일 일정 종료일(date)은 배타적이므로 그대로 둡니다.
            start = datetime.fromisoformat(start_raw["date"]).replace(tzinfo=tz)
            end = datetime.fromisoformat(end_raw["date"]).replace(tzinfo=tz)
        else:
            # datetime.fromisoformat 은 3.12 에서 끝의 Z 와 오프셋을 모두 파싱합니다.
            start = datetime.fromisoformat(start_raw["dateTime"])
            end = datetime.fromisoformat(end_raw["dateTime"])

        attendees = [
            a["email"]
            for a in resource.get("attendees", []) or []
            if a.get("email")
        ]
        organizer = (resource.get("organizer") or {}).get("email", "")

        return cls(
            id=resource.get("id", ""),
            summary=resource.get("summary") or "(제목 없음)",
            start=start,
            end=end,
            all_day=all_day,
            attendees=attendees,
            location=resource.get("location", "") or "",
            description=resource.get("description", "") or "",
            organizer=organizer,
            html_link=resource.get("htmlLink", "") or "",
            updated=resource.get("updated", "") or "",
        )
