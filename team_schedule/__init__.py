"""구글 캘린더 기반 팀 공유 일정 워크플로우 패키지.

핵심 로직은 모두 표준 라이브러리만 사용하며, 구글 API는 ``gcal`` 모듈에서만
(함수 안에서 지연 import 로) 쓰입니다. 따라서 구글 라이브러리가 없어도
이 패키지는 정상적으로 import 됩니다.
"""

from .config import Config
from .models import Event
from .notify import SlackNotifier
from .overlap import find_duplicates, find_overlaps
from .recurring import RecurringSpec, build_rrule
from .state import SeenState
from .summary import daily_summary, weekly_summary

__all__ = [
    "Event",
    "find_overlaps",
    "find_duplicates",
    "daily_summary",
    "weekly_summary",
    "SeenState",
    "SlackNotifier",
    "RecurringSpec",
    "build_rrule",
    "Config",
]
