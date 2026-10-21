"""team_schedule 웹 UI (FastAPI + SQLite).

브라우저에서 팀 일정을 조회/추가/수정/삭제할 수 있는 서버 렌더링 웹 앱입니다.
기존 도메인 로직(`team_schedule.models`, `overlap`, `summary`)을 그대로 재사용하며,
저장소만 JSON 대신 표준 라이브러리 ``sqlite3`` 로 구현했습니다.

실행:

    uvicorn team_schedule.web.app:app --reload
    # 또는
    python -m team_schedule.web

구글 캘린더 자격 증명 없이도 (SQLite DB 만으로) 동작하고 테스트할 수 있습니다.
"""

from .db import ScheduleDB, SqliteSeenStore

__all__ = ["ScheduleDB", "SqliteSeenStore", "create_app"]


def create_app(*args, **kwargs):
    """``app.create_app`` 의 지연 로더.

    FastAPI 미설치 환경에서도 ``import team_schedule.web`` 가 깨지지 않도록
    실제 import 는 호출 시점으로 미룹니다.
    """
    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)
