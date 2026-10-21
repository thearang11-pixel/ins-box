"""구글 캘린더 클라이언트.

주의: ``google-api-python-client`` 와 ``google-auth`` 는 **이 모듈에서만** 필요하며,
import 는 함수 안에서 지연으로 수행합니다. 따라서 구글 라이브러리가 설치돼 있지
않아도 ``import team_schedule`` 및 테스트는 정상 동작합니다.
"""

from __future__ import annotations

from datetime import datetime

from .models import Event
from .recurring import RecurringSpec


def _rfc3339(dt: datetime) -> str:
    return dt.isoformat()


class GoogleCalendarClient:
    """구글 캘린더 v3 서비스를 감싸는 얇은 래퍼."""

    def __init__(self, service, calendar_id: str):
        self.service = service
        self.calendar_id = calendar_id

    @classmethod
    def from_service_account_file(
        cls,
        path: str,
        calendar_id: str,
        scopes=("https://www.googleapis.com/auth/calendar",),
    ) -> "GoogleCalendarClient":
        """서비스 계정 키 파일로 클라이언트를 만듭니다(지연 import)."""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            path, scopes=list(scopes)
        )
        service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        return cls(service, calendar_id)

    def list_events(
        self, time_min: datetime, time_max: datetime, max_results: int = 250
    ) -> list[Event]:
        """기간 내 일정을 가져와 :class:`Event` 리스트로 변환합니다."""
        response = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=_rfc3339(time_min),
                timeMax=_rfc3339(time_max),
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
            )
            .execute()
        )
        return [Event.from_google(item) for item in response.get("items", [])]

    def create_event(self, body: dict) -> dict:
        """단일 일정을 생성합니다."""
        return (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=body)
            .execute()
        )

    def create_recurring(self, spec: RecurringSpec) -> dict:
        """반복 일정을 생성합니다."""
        return self.create_event(spec.to_google_body())
