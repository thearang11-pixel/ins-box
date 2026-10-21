"""Slack 알림 전송 및 메시지 포매팅 (urllib 사용, requests 의존성 없음)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

from .models import Event


class SlackNotifier:
    """Slack Incoming Webhook 으로 메시지를 보냅니다."""

    def __init__(self, webhook_url: str | None, dry_run: bool = False):
        self.webhook_url = webhook_url
        self.dry_run = dry_run
        self.sent: list[dict] = []

    def post(self, text: str, blocks=None) -> dict:
        """웹훅으로 JSON 페이로드를 POST 합니다.

        ``dry_run`` 이면 실제로 보내지 않고 페이로드를 저장/반환합니다(테스트용).
        2xx 가 아니면 명확한 오류를 냅니다.
        """
        payload: dict = {"text": text}
        if blocks is not None:
            payload["blocks"] = blocks

        if self.dry_run:
            self.sent.append(payload)
            return payload

        if not self.webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL 이 설정되어 있지 않습니다")

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status = getattr(response, "status", response.getcode())
                if not 200 <= status < 300:
                    raise RuntimeError(f"Slack 전송 실패: HTTP {status}")
        except urllib.error.HTTPError as exc:  # pragma: no cover - 네트워크 경로
            raise RuntimeError(f"Slack 전송 실패: HTTP {exc.code}") from exc
        return payload


def _fmt_time(event: Event, tzinfo: ZoneInfo) -> str:
    if event.all_day:
        return "종일"
    start = event.start.astimezone(tzinfo) if event.start.tzinfo else event.start
    end = event.end.astimezone(tzinfo) if event.end.tzinfo else event.end
    return f"{start:%Y-%m-%d %H:%M}–{end:%H:%M}"


def format_new_event(event: Event, tz: str = "Asia/Seoul") -> str:
    """새로 감지된 일정을 Slack mrkdwn 메시지로."""
    tzinfo = ZoneInfo(tz)
    lines = [f"🆕 *{event.summary}*", f"🕒 {_fmt_time(event, tzinfo)}"]
    if event.location:
        lines.append(f"📍 {event.location}")
    if event.attendees:
        lines.append(f"👥 {', '.join(event.attendees)} ({len(event.attendees)}명)")
    if event.html_link:
        lines.append(f"🔗 {event.html_link}")
    return "\n".join(lines)


def format_conflicts(overlaps, duplicates, tz: str = "Asia/Seoul") -> str:
    """겹치는 일정/중복 일정을 요약한 Slack 메시지. 비어 있어도 안전."""
    tzinfo = ZoneInfo(tz)
    if not overlaps and not duplicates:
        return "충돌하는 일정이 없습니다"

    lines: list[str] = []
    if overlaps:
        lines.append("⚠️ *겹치는 일정*")
        for first, second in overlaps:
            lines.append(
                f"• {first.summary} ({_fmt_time(first, tzinfo)})"
                f" ↔ {second.summary} ({_fmt_time(second, tzinfo)})"
            )
    if duplicates:
        lines.append("♻️ *중복 일정*")
        for group in duplicates:
            names = ", ".join(e.summary for e in group)
            lines.append(f"• {names} ({len(group)}건)")
    return "\n".join(lines)
