"""명령줄 인터페이스. ``python -m team_schedule ...`` 로 실행합니다."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from . import workflow
from .config import Config
from .notify import SlackNotifier
from .recurring import RecurringSpec, Weekday, build_rrule


def _build_client(config: Config, *, need_google: bool = True, need_slack: bool = True):
    config.validate(need_google=need_google, need_slack=need_slack)
    from .gcal import GoogleCalendarClient  # 지연 import

    return GoogleCalendarClient.from_service_account_file(
        config.service_account_file, config.calendar_id
    )


def _build_spec(args, timezone: str) -> RecurringSpec:
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    until = datetime.fromisoformat(args.until) if args.until else None
    byday = None
    if args.byday:
        byday = [Weekday(tok.strip().upper()) for tok in args.byday.split(",")]
    attendees = [a.strip() for a in args.attendees.split(",")] if args.attendees else []
    rrule = build_rrule(
        args.freq, interval=args.interval, count=args.count, until=until, byday=byday
    )
    return RecurringSpec(
        summary=args.summary,
        start=start,
        end=end,
        rrule=rrule,
        attendees=attendees,
        timezone=timezone,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="team_schedule", description="구글 캘린더 팀 공유 일정 워크플로우"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("notify-new", help="새 일정을 Slack 으로 알림")

    p_sum = sub.add_parser("summary", help="일정 요약을 Slack 으로 전송")
    group = p_sum.add_mutually_exclusive_group()
    group.add_argument("--daily", action="store_true", help="하루 요약(기본)")
    group.add_argument("--weekly", action="store_true", help="주간 요약")
    p_sum.add_argument("--date", help="YYYY-MM-DD (일간 요약 날짜)")

    sub.add_parser("check-conflicts", help="겹침/중복 일정 점검 후 알림")

    p_rec = sub.add_parser("add-recurring", help="반복 일정 추가")
    p_rec.add_argument("--summary", required=True)
    p_rec.add_argument("--start", required=True, help="ISO8601 (예: 2026-01-05T09:00:00+09:00)")
    p_rec.add_argument("--end", required=True, help="ISO8601")
    p_rec.add_argument("--freq", required=True, help="DAILY/WEEKLY/MONTHLY/YEARLY")
    p_rec.add_argument("--interval", type=int, default=1)
    p_rec.add_argument("--byday", help="예: MO,WE,FR")
    p_rec.add_argument("--count", type=int)
    p_rec.add_argument("--until", help="ISO8601")
    p_rec.add_argument("--attendees", help="쉼표로 구분한 이메일")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = Config.from_env()

    try:
        if args.command == "notify-new":
            client = _build_client(config)
            notifier = SlackNotifier(config.slack_webhook_url)
            posted = workflow.notify_new_events(client, config, notifier)
            print(f"새 일정 {len(posted)}건을 알렸습니다")
        elif args.command == "summary":
            client = _build_client(config)
            notifier = SlackNotifier(config.slack_webhook_url)
            if args.weekly:
                workflow.post_weekly_summary(client, config, notifier)
                print("주간 요약을 전송했습니다")
            else:
                day = datetime.fromisoformat(args.date).date() if args.date else None
                workflow.post_daily_summary(client, config, notifier, day=day)
                print("일간 요약을 전송했습니다")
        elif args.command == "check-conflicts":
            client = _build_client(config)
            notifier = SlackNotifier(config.slack_webhook_url)
            result = workflow.report_conflicts(client, config, notifier)
            print("충돌 일정을 전송했습니다" if result else "충돌 일정이 없습니다")
        elif args.command == "add-recurring":
            client = _build_client(config, need_slack=False)
            spec = _build_spec(args, config.timezone)
            created = workflow.add_recurring(client, spec)
            print(f"반복 일정을 생성했습니다: {created.get('id', '')}")
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
