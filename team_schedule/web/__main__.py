"""``python -m team_schedule.web`` 진입점.

환경변수로 간단히 설정할 수 있습니다.

- ``TEAM_SCHEDULE_DB``       : SQLite 파일 경로 (기본 ``team_schedule.db``)
- ``TEAM_SCHEDULE_WEB_HOST`` : 바인드 호스트 (기본 ``127.0.0.1``)
- ``TEAM_SCHEDULE_WEB_PORT`` : 포트 (기본 ``8000``)
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("TEAM_SCHEDULE_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("TEAM_SCHEDULE_WEB_PORT", "8000"))
    uvicorn.run("team_schedule.web.app:app", host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    main()
