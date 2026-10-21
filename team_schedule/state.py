"""처리한 일정 상태를 JSON 파일로 저장/비교 (순수 표준 라이브러리)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .models import Event


@dataclass
class SeenState:
    """일정 id -> updated 타임스탬프 매핑을 보관."""

    seen: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path) -> "SeenState":
        """파일에서 상태를 읽습니다(없으면 빈 상태)."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return cls(seen=dict(data))

    def is_empty(self) -> bool:
        return not self.seen

    def diff(self, events: list[Event]) -> tuple[list[Event], list[Event]]:
        """(새 일정, 변경된 일정) 을 돌려줍니다.

        - 새 일정: id 가 상태에 없는 일정
        - 변경된 일정: id 는 있지만 updated 가 달라진 일정
        """
        new_events: list[Event] = []
        updated_events: list[Event] = []
        for event in events:
            if event.id not in self.seen:
                new_events.append(event)
            elif self.seen[event.id] != event.updated:
                updated_events.append(event)
        return new_events, updated_events

    def mark(self, events: list[Event]) -> None:
        """현재 일정들의 상태를 기록합니다."""
        for event in events:
            self.seen[event.id] = event.updated

    def save(self, path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.seen, fh, ensure_ascii=False, indent=2)

    @classmethod
    def prime(cls, events: list[Event], path) -> "SeenState":
        """첫 실행용: 현재 일정 전부를 알림 없이 '본 것'으로 기록."""
        state = cls.load(path)
        state.mark(events)
        state.save(path)
        return state
