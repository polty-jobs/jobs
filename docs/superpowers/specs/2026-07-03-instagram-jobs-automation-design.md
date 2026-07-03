# Instagram Jobs Automation — Design

**Status**: Draft (pending user approval)
**Date**: 2026-07-03
**Owner**: hayechoi

## 1. Goal

3개 웹사이트에서 정치/공공 채용공고를 자동으로 수집해서, 하루 2회 (KST 10:00, 18:00) 인스타그램 비즈니스 계정에 다이제스트 형태로 게시한다.

**소스:**
1. 국회 의원실채용 — https://assembly.go.kr/portal/bbs/B0000038/list.do?menuNo=600097 (카테고리: 국회)
2. 국회 국회채용 — https://assembly.go.kr/portal/cnts/cntsCont/dataA.do?menuNo=600107&cntsDivCd=JOB (카테고리: 국회)
3. 셀럽어스 — https://www.selub.us/recruit/all (카테고리: 지방의회, "지방의회" 카테고리로만 필터)

**포스트 형태**: 1080×1350 (4:5) 단일 이미지, "국회" + "지방의회" 2섹션으로 분할. 카테고리별로 소속·제목·마감일 리스트업.

## 2. Non-Goals

- 공고 상세 페이지 클릭 유도 (프로필 링크트리로 우회)
- 실시간(< 12시간) 알림
- 개별 공고 1건당 포스트
- 인스타 스토리, 릴스, 리그램
- 크로스포스팅 (X/페이스북/스레드 등)
- 지원자 트래킹 / 리다이렉트 링크 단축
- 다른 사이트로의 확장은 이번 스코프 밖 (소스 인터페이스만 추상화)

## 3. High-Level Architecture

```
GitHub Actions cron (UTC 01:00, 09:00 = KST 10:00, 18:00)
        ↓
    main.py (오케스트레이터)
        ↓ 병렬 fetch
  ┌─────────────┼─────────────┐
  ▼             ▼             ▼
assembly_bbs  assembly_dataA  selub_local
  (bs4)         (bs4)          (Playwright)
        └──────┬──────┘
               ▼
        dedup filter (state.json)
               ↓
       (새 공고 있음?) → 없음 → 종료
               ↓ 있음
        render HTML → PNG (Playwright)
               ↓
        commit posts/{ts}.png + push  (raw URL 확보용)
               ↓
        Instagram Graph API: container → publish
               ↓
        commit state.json + push
               ↓
              완료
```

**병렬성/격리**: 3개 소스는 병렬로 fetch, 개별 실패는 로그만 남기고 나머지 진행. 전부 실패해야 워크플로 fail.

## 4. Project Structure

```
career/
├── .github/workflows/
│   ├── post.yml          # cron 스케줄 + 수동 workflow_dispatch
│   └── test.yml          # PR/push 시 pytest
├── src/
│   ├── main.py           # 오케스트레이터 (CLI: --dry-run, --output-dir 등)
│   ├── config.py         # env 로딩, KST 타임존, 상수
│   ├── sources/
│   │   ├── base.py       # JobItem 데이터클래스, Source 인터페이스
│   │   ├── assembly_bbs.py
│   │   ├── assembly_dataA.py
│   │   └── selub.py
│   ├── state.py          # state.json I/O, dedup, bootstrap 판별
│   ├── render.py         # Jinja 렌더 → Playwright 스크린샷
│   ├── instagram.py      # Graph API 클라이언트
│   └── templates/
│       ├── digest.html.j2
│       └── digest.css
├── tests/
│   ├── fixtures/         # 각 소스 HTML 샘플
│   ├── snapshots/        # 렌더링 스냅샷
│   ├── test_sources.py
│   ├── test_state.py
│   ├── test_render.py
│   └── test_instagram.py # HTTP mock
├── posts/                # 업로드된 이미지 아카이브 (git 저장)
├── state.json            # dedup 상태 (git 저장)
├── requirements.txt
├── .env.example
└── README.md
```

## 5. Data Model

```python
from dataclasses import dataclass
from datetime import date, datetime

@dataclass(frozen=True)
class JobItem:
    source: str            # "assembly_bbs" | "assembly_dataA" | "selub_local"
    category: str          # "국회" | "지방의회"
    external_id: str       # 소스별 고유 번호
    title: str
    org: str               # 담당부서/의원실/기관명
    deadline: date | None  # 마감일 (없거나 파싱 실패 시 None)
    url: str               # 절대 URL
    fetched_at: datetime

    def dedup_key(self) -> str:
        return f"{self.source}:{self.external_id}"
```

**Source 인터페이스:**
```python
class Source(Protocol):
    name: str            # dedup key prefix
    category: str        # "국회" | "지방의회"

    def fetch(self) -> list[JobItem]:
        """페이지 1(및 필요 시 2)의 진행중 공고 반환. 실패 시 예외."""
```

## 6. Source Details

### 6.1 assembly_bbs — 국회 의원실채용
- **URL**: `https://assembly.go.kr/portal/bbs/B0000038/list.do?menuNo=600097` + `sttus=진행중` 쿼리
- **파싱**: requests + BeautifulSoup4
- **필드**:
  - `external_id` ← 번호 열
  - `title` ← 제목 링크 텍스트 (앞뒤 공백 strip)
  - `org` ← 담당부서 열
  - `deadline` ← 기간 열의 두 번째 날짜 (`YYYY-MM-DD ~ YYYY-MM-DD` → 뒷부분)
  - `url` ← 제목 링크 (rel → abs)
  - `category` = `"국회"` 상수
- **페이지**: 1부터. 페이지 1에 새 공고 10건 다 있으면 페이지 2까지 (안전 마진)
- **요청 간격**: `time.sleep(1)` between paginated requests

### 6.2 assembly_dataA — 국회 국회채용
- **URL**: `https://assembly.go.kr/portal/cnts/cntsCont/dataA.do?menuNo=600107&cntsDivCd=JOB`
- **파싱**: requests + BeautifulSoup4
- **필드**:
  - `external_id` ← 번호 열
  - `title` ← 제목
  - `org` ← 소속기관명
  - `deadline` ← 리스트뷰에 없음 → **새 아이템(dedup 통과분)에 한해서만** 상세 페이지 fetch로 파싱. 못 찾으면 `None`
  - `url` ← 상세 링크 (rel → abs)
  - `category` = `"국회"` 상수
- **주의**: 상세 페이지 요청은 새 아이템 수만큼만 (state.json으로 걸러진 뒤)

### 6.3 selub_local — 셀럽어스 지방의회
- **URL**: `https://www.selub.us/recruit/all`
- **파싱**: **Playwright** (JS 렌더링). 페이지 열고 "지방의회" 카테고리 탭 클릭 + "진행중" 필터 적용, 리스트 렌더 대기 후 DOM 파싱
- **최적화 (구현 초반 조사)**: Network 탭에서 JSON XHR 엔드포인트 발견 시 `requests`로 직접 호출로 전환 → Playwright 안 씀
- **필드**: 실제 페이지 보고 확정. 대략:
  - `external_id` ← URL slug 또는 data-id
  - `title` ← 제목
  - `org` ← 의회명 / 소속
  - `deadline` ← 마감일 (파싱 실패 시 None)
  - `url` ← 상세 링크 (abs)
  - `category` = `"지방의회"` 상수
- **robots.txt**: 구현 시작 시 확인. 명시적 disallow면 셀럽어스 소스 제외 재검토
- **rate limit**: 요청 간격 1초, 카테고리 탭 클릭 후 렌더 완료 대기(최대 15초)
- **Selector 실패 계약**: "지방의회" 탭 · "진행중" 필터 · 리스트 컨테이너 selector가 못 찾히면 → **예외 발생 (fetch 실패로 처리)**. Section 10 규칙에 따라 warn 로그 + 다른 2개 소스는 진행

## 7. State Management & Dedup

### 파일: `state.json` (git으로 관리)
```json
{
  "version": 1,
  "last_run_at": "2026-07-03T10:00:00+09:00",
  "seen": {
    "assembly_bbs":   ["9554", "9553", ...],
    "assembly_dataA": ["4842", "4841", ...],
    "selub_local":    ["abc123", "def456", ...]
  }
}
```

### 규칙
- Dedup key: `f"{source}:{external_id}"`. `seen`은 source별로 external_id 배열 유지 (JSON 편의)
- **FIFO 프룬**: 소스별 최근 500개만 유지. 커밋 전 프룬
- **Bootstrap**: state.json 부재 or `seen` 전부 빈 배열이면 → 현재 페이지 1 아이템 전부를 `seen`에 넣고 종료 (포스트 안 함, 스팸 방지)
- 새 아이템은 "seen에 없는 external_id" = "새 공고"

### 커밋 순서 (원자성 보장)
1. Fetch + dedup 계산
2. **새 공고 0건** → 종료 (커밋 없음)
3. **있음**: 이미지 렌더 → `posts/{YYYY-MM-DD-HHmm}.png` 커밋 & push
4. 인스타 container 생성 (URL fetch 확인) → publish
5. state.json 프룬 + 업데이트 → 커밋 & push (2번째 커밋)

**실패 시맨틱스:**
- 4번 실패 → 3번의 이미지 커밋은 남지만, state.json 미갱신 → 다음 실행에서 새로 렌더 & 새 파일명으로 커밋. **orphan PNG는 아카이브로 유지 (자동 정리 스코프 밖)**. 파일명이 `{YYYY-MM-DD-HHmm}.png`라 겹칠 위험 없음
- 5번 실패 → 인스타는 이미 게시됨. 커밋 재시도 3회(pull-rebase). 그래도 실패면 알림 → 수동 병합
- Push 충돌 (누군가 리포에 다른 커밋): `git pull --rebase` 후 재시도

### GitHub Actions 권한
- 워크플로에 `permissions: contents: write`
- `actions/checkout@v4` with `persist-credentials: true`
- 커밋 identity: `github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>`

## 8. Rendering

### 스펙
- 출력: **1080×1350 PNG** (Instagram 4:5)
- 방식: Jinja2 → HTML → Playwright(chromium headless) → screenshot
- 폰트: **Pretendard** (한국어 최적화). Actions runner에서 `apt-get install -y fonts-pretendard` 시도 실패 시 GitHub raw / npm으로 fallback. 또는 Google Fonts CDN + Playwright 로컬 캐시

### 템플릿 (요약)
```html
<div class="page sz-{{ size_class }}">
  <header>
    <div class="date">{{ date_kst }} · {{ session_label }}</div>
    <h1>오늘의 새 공고 · 국회 {{ items_국회|length }} · 지방의회 {{ items_지방의회|length }}</h1>
  </header>

  {% if items_국회 %}
  <section class="cat">
    <div class="cat-label">국회</div>
    <ul>
      {% for it in items_국회 %}
      <li>· {{ it.org }} · {{ it.title }}{% if it.deadline %} · ~{{ it.deadline|shortdate }}{% endif %}</li>
      {% endfor %}
    </ul>
  </section>
  {% endif %}

  {% if items_지방의회 %}
  <section class="cat">
    <div class="cat-label">지방의회</div>
    <ul>...</ul>
  </section>
  {% endif %}

  <footer class="brand">@{{ ig_handle }}</footer>
</div>
```

### 동적 폰트 스케일
- `size_class` = total 아이템 수 기준 4단계: `1` (≤10), `2` (11-20), `3` (21-30), `4` (31+)
- CSS에서 클래스별 폰트/줄간격 정의
- 렌더 후 페이지 JS로 overflow 감지 → 감지 시 `sz-4` 강제
- **`sz-4`에서도 overflow면 (매우 드물지만 40+/day 시나리오)**: 각 카테고리 리스트를 뒤에서부터 잘라내고 마지막에 `· 외 N건` 표기. "전부 표기" 원칙의 안전장치. 캡션에는 원 카운트 유지

### 컬러/스타일
- 배경: `#1e3a5f` (다크 네이비)
- 텍스트: 흰색 계열 (`#fff` / `#e8ecf1`)
- Cat label: 얇은 대문자, 하단 1px 구분선
- 카테고리 섹션 간 여백

### 시간대
- Cron은 UTC지만 렌더 안의 날짜/`session_label`은 **KST**
- `session_label` 결정: KST hour == 10 → "AM 10시", KST hour == 18 → "PM 6시" (main.py가 파라미터로 넘김)

## 9. Instagram Upload

### 접근
- Graph API v19.0+
- Business Account + FB Page 연결됨 (사용자 확인)
- Long-lived access token (60일 갱신 자동화는 추후 스코프)

### 이미지 호스팅 (URL 요구사항)
- Graph API는 이미지 URL을 요구 (파일 업로드 아님)
- 전략: 렌더된 PNG를 `posts/{YYYY-MM-DD-HHmm}.png`로 커밋 & push → GitHub raw URL 사용
- Raw URL 예: `https://raw.githubusercontent.com/{owner}/{repo}/main/posts/2026-07-03-1000.png`
- 아카이브 성격 겸함 (누적 부담 낮음: 최대 2/일 × 400KB × 365 = ~290MB/년)

### 2단계 호출
1. **Container 생성**
   ```
   POST /v19.0/{IG_BUSINESS_ID}/media
     image_url={raw url}
     caption={caption}
     access_token={TOKEN}
   → creation_id
   ```
2. **Status 폴링** (선택, in_progress → finished 대기)
   ```
   GET /v19.0/{creation_id}?fields=status_code
   ```
   최대 60초, 2초 간격
3. **Publish**
   ```
   POST /v19.0/{IG_BUSINESS_ID}/media_publish
     creation_id={creation_id}
     access_token={TOKEN}
   → post_id
   ```

### Caption 템플릿
```
[일일 채용 브리핑 · {session_label}]
{summary_line}

원문 링크는 프로필의 링크트리 참고

#국회채용 #의원실채용 #지방의회채용 #공공채용
```

- `summary_line` = 새 공고가 있는 카테고리만 join (이미지 섹션 렌더 룰과 매치)
  - 국회 3, 지방의회 2 → `"국회 3건 · 지방의회 2건"`
  - 국회 3, 지방의회 0 → `"국회 3건"` (지방의회 언급 생략)
  - 지방의회 2, 국회 0 → `"지방의회 2건"`
  - 둘 다 0 → 포스트 자체가 발생 안 함 (Section 3의 "0건 스킵")

### Secrets (GitHub Actions Secrets)
- `IG_ACCESS_TOKEN` — Instagram Graph API long-lived token
- `IG_BUSINESS_ACCOUNT_ID` — Instagram 비즈니스 계정 ID
- `GITHUB_TOKEN` — checkout/push용 (Actions 자동 제공)

## 10. Error Handling & Observability

### 실패 격리 & 재시도

| 단계 | 실패 | 처리 |
|------|------|------|
| 개별 소스 fetch | 특정 소스 timeout/파싱 오류 | warn 로그, 나머지 소스 진행 |
| 모든 소스 fetch 실패 | 3개 다 실패 | exit 1, 이메일 알림 |
| 렌더링 | 폰트 로드 실패, Playwright 오류 | 재시도 1회 (다른 폰트 fallback), 실패 시 exit 1 |
| 이미지 커밋/push | conflict | `git pull --rebase` + 재시도 3회 |
| IG container | HTTP 5xx | 5초 뒤 재시도 1회 |
| IG publish | HTTP 5xx | 5초 뒤 재시도 1회 |
| state.json push | conflict | `git pull --rebase` + 재시도 3회. IG 이미 게시됨 → 수동 병합 알림 |

### 로그
- 표준 출력에 구조화 로그: JSON one-line per event (fetch, filter, render, upload, commit)
- GitHub Actions 워크플로 로그에 자동 캡처

### 알림
- 기본: GitHub Actions 실패 이메일 (계정 설정)
- 선택 확장: `SLACK_WEBHOOK_URL` secret 있으면 실패 시 웹훅 호출 (스코프 안, 최소 구현)

## 11. Testing Strategy

### Unit
- `tests/test_sources.py`: 각 소스 파서, `tests/fixtures/{source}-page1.html` 저장본 사용. 실제 HTTP 안 함
- `tests/test_state.py`: dedup, FIFO 프룬, bootstrap 판정
- `tests/test_render.py`: 템플릿 렌더링 후 DOM 구조 검증 (예: `국회` 섹션에 li 개수, 카테고리 empty 시 섹션 제거)
- `tests/test_instagram.py`: HTTP 모킹(responses/httpretty)으로 container→publish 시퀀스, 재시도, 실패

### Integration
- `python -m src.main --dry-run --output-dir ./out`: 실제 사이트 fetch까지, 렌더 PNG 저장, IG 업로드/커밋 스킵
- `--fixture-mode`: fixture HTML만 소스로 사용해서 이미지 회귀 확인

### Snapshot
- `tests/test_render_snapshot.py`: 3~5개 시나리오 (0건, 1건씩, 15건씩, 30건 편중, deadline 결측 혼재)
- **PNG SHA256 비교는 하지 않음** (Chromium/폰트 버전에 지나치게 취약해 false-positive 다발)
- 대신 두 가지 검증 조합:
  1. **HTML 스냅샷**: 최종 렌더된 HTML을 `tests/snapshots/*.html`과 diff (구조/텍스트 회귀 감지)
  2. **PNG perceptual diff**: `pixelmatch` (또는 유사 라이브러리)로 `tests/snapshots/*.png`와 threshold 비교 (기본 0.05 정도) — 폰트 렌더 미세차는 통과, 레이아웃 붕괴는 감지

### CI (`.github/workflows/test.yml`)
- push/PR 시: pytest 전체
- 매일 06:00 UTC (KST 15:00): `--dry-run`으로 실사이트 selector sanity check → 실패 시 알림 (사이트 개편 조기 감지)

## 12. Setup Prerequisites (사용자 액션 필요)

문서 확정 후 구현 착수 전에:

1. **인스타 Graph API 세팅 완료** (사용자 상태: 3/4 완료)
   - [x] 비즈니스/크리에이터 계정
   - [x] FB 페이지 연결
   - [x] Meta for Developers 앱 등록
   - [ ] Instagram Graph API product 추가 + `instagram_content_publish` 권한 신청 → **app review 필요** (수일 소요 가능)
   - [ ] Long-lived access token 발급 (60일 유효, 갱신은 추후)
   - [ ] `IG_BUSINESS_ACCOUNT_ID` 조회

2. **GitHub 리포 생성**
   - 리포 이름 확정 (예: `career-jobs-ig-bot`)
   - private 권장 (state.json에는 민감정보 없음, 그래도 posts/ 아카이브 사적 사용 가능)
   - `IG_ACCESS_TOKEN`, `IG_BUSINESS_ACCOUNT_ID` Secrets 등록

3. **셀럽어스 robots.txt 확인**
   - `https://www.selub.us/robots.txt` 확인
   - 명시적 disallow면 소스에서 제외 재논의

4. **폰트 라이센스**
   - Pretendard: SIL Open Font License 1.1 (상업/재배포 무료)
   - 문제 없음

## 13. Open Questions / Deferred

- **인스타 handle 확정**: 목업의 `assembly_jobs`는 placeholder. 실제 계정 이름 확정 후 config에 반영
- **Long-lived token 자동 갱신**: 60일마다 갱신 필요. 초기 스코프는 수동 갱신, 이후 워크플로에 갱신 스텝 추가 검토
- **셀럽어스 상세 필드**: 실제 페이지 렌더 후 selector 확정 (구현 초반 태스크)
- **폰트 로드 방식**: Actions에서 Pretendard 설치 최적 경로 (system font vs CDN vs commit vendored) — 실측 뒤 확정
- **인스타 caption 링크 이슈**: IG 캡션의 URL은 클릭 불가. "프로필 링크트리 참고" 문구로 우회
- **다중 인스타 계정 지원**: 스코프 밖. 단일 계정만
