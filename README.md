# ins-box

텍스트 둘레에 상자를 그려주는 작은 파이썬 패키지예요. 한글처럼 폭이 넓은 문자도 줄이 맞게 그려요.

```python
from ins_box import box

print(box("안녕하세요\nhello"))
```

```
┌────────────┐
│ 안녕하세요 │
│ hello      │
└────────────┘
```

## 테스트 실행

```bash
pip install pytest
pytest
```

`main` 브랜치에 푸시하거나 PR을 열면 GitHub Actions에서 테스트가 자동으로 실행돼요.

## 팀 공유 일정 워크플로우 (team_schedule)

구글 캘린더(공유 캘린더)를 기반으로 팀 일정을 자동으로 관리하는 패키지예요.
핵심 로직은 모두 파이썬 표준 라이브러리로만 작성되어 있고, 구글 API는
`team_schedule/gcal.py` 안에서만 **지연 import** 로 사용돼요. 덕분에 구글
라이브러리를 설치하지 않아도 `import team_schedule` 와 테스트가 잘 돌아가요.
Slack 전송도 `urllib` 만 쓰기 때문에 `requests` 같은 외부 의존성이 없어요.

### 네 가지 흐름

1. **새 일정 알림(`notify-new`)** — 다가오는 일정을 조회해서 이전에 못 보던
   새 일정을 Slack 으로 알려줘요. 상태 파일로 중복 알림을 막고, 첫 실행에는
   현재 일정을 조용히 기록(prime)만 해서 폭탄 알림을 피해요.
2. **일정 요약(`summary`)** — 하루(`--daily`) 또는 한 주(`--weekly`) 일정을
   한국어로 정리해 Slack 으로 보내요.
3. **충돌 점검(`check-conflicts`)** — 기간 내 겹치는 일정과 중복(제목이 같고
   시간이 겹치는) 일정을 찾아 있을 때만 알려줘요.
4. **반복 일정 추가(`add-recurring`)** — RFC5545 RRULE 을 만들어 반복 일정을
   공유 캘린더에 생성해요.

### 설치

```bash
pip install -r requirements.txt
```

`requirements.txt` 의 구글 패키지는 **실제 구글 캘린더 접근에만** 필요해요.
테스트만 돌릴 거면 `pip install pytest` 만으로 충분해요.

### 구글 서비스 계정 만들기 + 캘린더 공유

1. [Google Cloud Console](https://console.cloud.google.com/) 에서 프로젝트를
   만들고 **Google Calendar API** 를 사용 설정해요.
2. **IAM 및 관리자 → 서비스 계정** 에서 서비스 계정을 만들고, 키를 **JSON**
   형식으로 내려받아요. 이 파일 경로를 `GOOGLE_SERVICE_ACCOUNT_FILE` 로 지정해요.
3. 공유하려는 구글 캘린더의 **설정 → 특정 사용자와 공유** 에서 위 서비스 계정
   이메일(`...@...iam.gserviceaccount.com`)을 추가하고, 반복 일정도 만들 거면
   **일정 변경** 권한을 줘요. (읽기만 하면 "모든 일정 세부정보 보기" 로 충분)
4. 캘린더 ID(설정 화면의 "캘린더 통합" 에 있는 값)를 `GOOGLE_CALENDAR_ID` 로
   지정해요.

### 환경변수

`.env.example` 를 참고하세요.

| 변수 | 설명 |
| --- | --- |
| `GOOGLE_CALENDAR_ID` | 공유 캘린더 ID |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | 서비스 계정 키(JSON) 파일 경로 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |
| `TEAM_SCHEDULE_STATE_FILE` | 상태 저장 파일 (기본 `.team_schedule_state.json`) |
| `TEAM_SCHEDULE_TZ` | 기준 시간대 (기본 `Asia/Seoul`) |

### CLI 사용 예시

```bash
# 새 일정 알림
python -m team_schedule notify-new

# 오늘 하루 요약 / 특정 날짜 요약 / 이번 주 요약
python -m team_schedule summary --daily
python -m team_schedule summary --daily --date 2026-01-05
python -m team_schedule summary --weekly

# 충돌(겹침/중복) 점검
python -m team_schedule check-conflicts

# 반복 일정 추가 (매주 월·수·금 09:00, 10회)
python -m team_schedule add-recurring \
  --summary "데일리 스탠드업" \
  --start 2026-01-05T09:00:00+09:00 \
  --end   2026-01-05T09:15:00+09:00 \
  --freq WEEKLY --byday MO,WE,FR --count 10 \
  --attendees a@example.com,b@example.com
```

### cron / GitHub Actions 스케줄 예시

`.github/workflows/team-schedule.yml` 에 매일 09:00 KST(00:00 UTC) 요약 +
새 일정 점검을 하는 스케줄 워크플로우가 들어 있어요. 이 워크플로우는
`push` / `pull_request` 로는 **실행되지 않아서** 기존 `test` CI 에 영향을 주지
않아요. 저장소 시크릿으로 `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_CALENDAR_ID`,
`SLACK_WEBHOOK_URL` 을 등록하면 돼요.

직접 cron 으로 돌리고 싶다면 (매일 09:00 KST):

```cron
0 9 * * *  cd /path/to/ins-box && python -m team_schedule notify-new && python -m team_schedule summary --daily
```

### 테스트

테스트는 **구글 라이브러리 없이** 돌아가요. 가짜 캘린더 클라이언트와
`SlackNotifier` 의 `dry_run` 모드를 써서 네트워크 없이 모든 흐름을 검증해요.

```bash
pip install pytest
pytest
```

웹 UI 라우트 테스트까지 함께 돌리려면 웹 의존성도 설치하세요.

```bash
pip install pytest httpx fastapi uvicorn jinja2 python-multipart
pytest
```

## 웹 UI (team_schedule.web) — 브라우저로 일정 보기/관리

Slack 밖에서도 팀원이 **브라우저로** 일정을 보고 관리할 수 있도록
**FastAPI + SQLite** 로 만든 서버 렌더링 웹 앱이에요. 프론트엔드 빌드
과정이 전혀 없고(Jinja2 서버 렌더링), **구글 자격 증명 없이도** 동작/테스트
할 수 있어요. 일정은 SQLite DB 에 저장돼요.

### 특징

- **FastAPI + Jinja2**: 빌드 단계 없는 순수 HTML. 데스크톱/모바일 반응형 CSS.
- **SQLite 저장소**: 표준 라이브러리 `sqlite3` 만 사용(추가 DB 의존성 없음).
  - `events` — 웹에서 관리하는 팀 일정(추가/수정/삭제 대상)
  - `seen_events` — 기존 JSON "이미 본 일정" 상태의 SQLite 버전
    (`team_schedule.web.db.SqliteSeenStore`). 여러 프로세스(cron 작업 + 웹 서버)가
    하나의 DB 파일을 공유할 수 있어요.
  - `notifications` — 웹에서 발생한 추가/수정/삭제 내역(최근 알림 내역 페이지)
- **도메인 로직 재사용**: 겹침/중복 탐지는 `team_schedule.overlap`, 요약은
  `team_schedule.summary` 를 그대로 **import** 해서 써요(중복 구현 없음).

### 페이지

| 경로 | 내용 |
| --- | --- |
| `/` | 대시보드 — 오늘/이번 주 요약(기존 요약 로직 재사용), 겹침/중복 건수 |
| `/events` | 일정 목록 — 날짜로 필터링, 겹침/중복 일정은 "충돌" 로 표시 |
| `/events/new` | 일정 추가 폼 |
| `/events/{id}/edit` | 일정 수정 폼 |
| `/notifications` | 최근 알림(추가/수정/삭제) 내역 |
| `/healthz` | 헬스 체크(JSON) |

### 실행

```bash
pip install fastapi uvicorn jinja2 python-multipart

# 방법 1
uvicorn team_schedule.web.app:app --reload

# 방법 2 (환경변수로 호스트/포트 조정 가능)
python -m team_schedule.web
```

기본값은 `http://127.0.0.1:8000` 이에요.

### 환경변수 (웹)

| 변수 | 설명 |
| --- | --- |
| `TEAM_SCHEDULE_DB` | SQLite 파일 경로 (기본 `team_schedule.db`) |
| `TEAM_SCHEDULE_TZ` | 기준 시간대 (기본 `Asia/Seoul`) |
| `TEAM_SCHEDULE_WEB_HOST` | 바인드 호스트 (기본 `127.0.0.1`) |
| `TEAM_SCHEDULE_WEB_PORT` | 포트 (기본 `8000`) |

### Slack/cron 흐름과의 관계

- 기존 **CLI/cron/Slack** 흐름(`notify-new`, `summary`, `check-conflicts`,
  `add-recurring`)은 **구글 캘린더**를 원본으로 삼고 Slack 으로 알림을 보내요.
- **웹 UI** 는 **SQLite DB** 를 원본으로 삼아 브라우저에서 보기/관리하게 해줘요.
  구글 연동은 선택 사항이라 자격 증명이 없어도 웹은 완전히 동작해요.
- 두 세계는 저장소를 공유할 수 있어요. 예를 들어 cron 워크플로우가 JSON 상태
  대신 `SqliteSeenStore(path)` 를 쓰면, 같은 SQLite 파일을 웹 서버와 공유하면서
  "이미 본 일정" 상태를 함께 관리할 수 있어요.
- (선택) 구글 캘린더와 양방향 동기화를 붙이고 싶다면 `team_schedule.gcal`
  (지연 import) 를 이용해 DB ↔ 캘린더 동기 계층을 추가로 얹을 수 있어요.
