"""환경변수 기반 설정 (순수 표준 라이브러리)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    """워크플로우 실행에 필요한 설정."""

    calendar_id: str = ""
    service_account_file: str = ""
    slack_webhook_url: str = ""
    state_file: str = ".team_schedule_state.json"
    timezone: str = "Asia/Seoul"

    @classmethod
    def from_env(cls, env=None) -> "Config":
        """환경변수에서 설정을 읽습니다."""
        if env is None:
            env = os.environ
        return cls(
            calendar_id=env.get("GOOGLE_CALENDAR_ID", ""),
            service_account_file=env.get("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
            slack_webhook_url=env.get("SLACK_WEBHOOK_URL", ""),
            state_file=env.get("TEAM_SCHEDULE_STATE_FILE", ".team_schedule_state.json"),
            timezone=env.get("TEAM_SCHEDULE_TZ", "Asia/Seoul"),
        )

    def validate(self, *, need_google: bool = True, need_slack: bool = True) -> None:
        """작업에 필요한 환경변수가 없으면 친절한 오류를 냅니다."""
        missing: list[str] = []
        if need_google:
            if not self.calendar_id:
                missing.append("GOOGLE_CALENDAR_ID")
            if not self.service_account_file:
                missing.append("GOOGLE_SERVICE_ACCOUNT_FILE")
        if need_slack and not self.slack_webhook_url:
            missing.append("SLACK_WEBHOOK_URL")
        if missing:
            raise ValueError(
                "다음 환경변수가 설정되어 있지 않습니다: " + ", ".join(missing)
            )
