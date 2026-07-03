# polty-jobs

3개 채용 사이트에서 새 공고를 수집해서 매일 KST 10시·18시에 인스타그램 [@polty.jobs](https://instagram.com/polty.jobs)에 다이제스트로 자동 업로드하는 봇.

## 소스
- **국회 의원실채용** — assembly.go.kr B0000038 (`assembly_bbs`)
- **국회 국회채용** — assembly.go.kr dataA?cntsDivCd=JOB (`assembly_dataA`)
- **셀럽어스 지방의회** — selub.us 내부 JSON API, `local-council` 필터 (`selub_local`)

## 아키텍처
GitHub Actions cron → Python 오케스트레이터 → 3소스 병렬 fetch → dedup(state.json) → HTML/Playwright PNG 렌더 → posts/에 커밋 → Instagram Graph API 게시 → state 커밋.

```
render                    publish
─────                     ───────
fetch sources             read pending.json
  ↓                         ↓
filter_new(state)         POST IG media (container)
  ↓                         ↓
render PNG                POST IG media_publish
  ↓                         ↓
write pending.json        record + save state.json
```

두 서브커맨드로 분리한 이유: Instagram Graph API가 이미지의 공개 URL을 요구하므로 워크플로가 render 후 이미지를 push해서 raw URL을 확보한 뒤 publish를 호출해야 함.

## 로컬 개발
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m playwright install chromium
cp .env.example .env  # 값 채우기
pytest
```

로컬 파이프라인 리허설:
```bash
python -m src.main render --state state.json --posts-dir posts --pending pending.json
cat pending.json
# 두 번째 실행부터 posts/*.png 렌더됨
```

## 배포 (GitHub Actions)
1. GitHub Secrets 등록:
   - `IG_ACCESS_TOKEN` — long-lived Instagram Graph API 토큰
   - `IG_BUSINESS_ACCOUNT_ID` — Instagram 비즈니스 계정 ID
2. (선택) 리포 variable `IG_HANDLE`은 워크플로 기본값 `polty.jobs`이므로 다른 계정 쓸 때만 세팅
3. `post` 워크플로가 KST 10:00, 18:00에 자동 실행됨. 최초 실행은 **bootstrap** — 기존 공고를 seen 처리하고 포스트 안 함. 다음 실행부터 새 공고만 게시.
4. 수동 실행: Actions 탭 → post → Run workflow → dry_run 체크로 안전 테스트 가능.

## 폴더 구조
```
polty-jobs/
├── .github/workflows/
│   ├── post.yml           # cron KST 10/18
│   └── test.yml           # PR/push 시 pytest+ruff
├── src/
│   ├── main.py            # render/publish 서브커맨드
│   ├── config.py          # KST, session_label, size_class, env
│   ├── state.py           # State.load/save, filter_new
│   ├── sources/
│   │   ├── base.py        # JobItem, Source Protocol
│   │   ├── assembly_bbs.py
│   │   ├── assembly_dataA.py
│   │   └── selub.py
│   ├── render.py          # Jinja + Playwright PNG
│   ├── instagram.py       # Graph API 클라이언트
│   └── templates/
│       ├── digest.html.j2
│       └── digest.css
├── tests/                 # pytest 스위트 + fixtures
├── posts/                 # 업로드 이미지 아카이브 (git)
├── state.json             # dedup 상태 (git)
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## 참고
- Instagram Graph API 세팅: [`docs/setup-instagram-graph-api.md`](docs/setup-instagram-graph-api.md)
- 설계: [`docs/superpowers/specs/2026-07-03-instagram-jobs-automation-design.md`](docs/superpowers/specs/2026-07-03-instagram-jobs-automation-design.md)
- 구현 계획: [`docs/superpowers/plans/2026-07-03-instagram-jobs-automation.md`](docs/superpowers/plans/2026-07-03-instagram-jobs-automation.md)
