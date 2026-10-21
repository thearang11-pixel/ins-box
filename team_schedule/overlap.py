"""일정 겹침/중복 탐지 (순수 표준 라이브러리)."""

from __future__ import annotations

import re

from .models import Event


def find_overlaps(events: list[Event]) -> list[tuple[Event, Event]]:
    """시간 구간이 겹치는 모든 일정 쌍을 한 번씩 돌려줍니다.

    시작 시각 기준으로 정렬한 뒤 각 쌍을 한 번씩만 검사합니다.
    """
    ordered = sorted(events, key=lambda e: e.start)
    pairs: list[tuple[Event, Event]] = []
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            # 정렬돼 있으므로 ordered[j].start >= ordered[i].start.
            # ordered[j] 가 ordered[i] 의 끝보다 뒤에서 시작하면 그 이후도 모두 뒤.
            if ordered[j].start >= ordered[i].end:
                break
            if ordered[i].overlaps(ordered[j]):
                pairs.append((ordered[i], ordered[j]))
    return pairs


def _normalize(summary: str) -> str:
    """제목을 정규화: 양끝 공백 제거 + 소문자 + 연속 공백 하나로."""
    return re.sub(r"\s+", " ", summary.strip().lower())


def find_duplicates(events: list[Event]) -> list[list[Event]]:
    """중복으로 추정되는 일정 그룹(크기 2 이상)을 돌려줍니다.

    정규화한 제목이 같고 시간이 겹치는 일정끼리 묶습니다.
    """
    ordered = sorted(events, key=lambda e: e.start)
    used: set[int] = set()
    groups: list[list[Event]] = []
    for i in range(len(ordered)):
        if i in used:
            continue
        group = [ordered[i]]
        for j in range(i + 1, len(ordered)):
            if j in used:
                continue
            if _normalize(ordered[i].summary) == _normalize(ordered[j].summary) and ordered[i].overlaps(ordered[j]):
                group.append(ordered[j])
                used.add(j)
        if len(group) >= 2:
            used.add(i)
            groups.append(group)
    return groups
