# Instagram Graph API 세팅 가이드

이 가이드는 폴티잡스 봇이 `@polty.jobs` 계정에 자동 게시하기 위한 IG Graph API 세팅 절차입니다.

## 1. 계정 준비
- 인스타 앱 → 프로필 → ≡ → 설정 → **계정 유형 전환** → **비즈니스** 또는 **크리에이터**로
- 페이스북 페이지 하나 생성 후 인스타 계정에 연결

## 2. Meta for Developers 앱 생성
1. https://developers.facebook.com/apps/ → **Create App**
2. Use case: **Other** → Type: **Business**
3. 앱 이름 (예: `polty-jobs-bot`), Contact email 입력

## 3. Instagram Graph API product 추가
1. 앱 대시보드 → **Add Product** → **Instagram Graph API** → **Set up**

## 4. 권한 신청 (App Review 필요)
필수 권한:
- `instagram_basic`
- `instagram_content_publish`
- `pages_show_list`
- `pages_read_engagement`

**App Review에는 수일~1주** 걸립니다. 심사 없이는 개발자 본인만 게시 가능하므로 개인 봇으로는 심사 없이도 동작합니다 (테스트 사용자 등록만 하면 됨).

## 5. Long-lived Access Token 발급
1. [Graph API Explorer](https://developers.facebook.com/tools/explorer/) 접속, 앱 선택
2. **User Token** 발급 시 위 4개 권한 체크
3. [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/)에서 **Extend Access Token** → 60일 long-lived 토큰
4. **Page Access Token**으로 교환 (같은 페이지에 대한 토큰. 봇이 실제 사용) — Graph API Explorer에서 페이지 선택 후 재발급 or `/me/accounts` 호출로 얻음

발급된 토큰을 GitHub Secrets `IG_ACCESS_TOKEN`에 저장.

## 6. Instagram Business Account ID 조회
```bash
# 페이지 목록
curl "https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_TOKEN"
# 그중 페이지 ID 확인 후:
curl "https://graph.facebook.com/v19.0/{PAGE_ID}?fields=instagram_business_account&access_token=YOUR_TOKEN"
# instagram_business_account.id 값이 IG_BUSINESS_ACCOUNT_ID
```
GitHub Secrets `IG_BUSINESS_ACCOUNT_ID`에 저장.

## 7. GitHub Secrets 등록
- `polty-jobs/jobs` 리포 → Settings → Secrets and variables → Actions → **New repository secret**
- `IG_ACCESS_TOKEN`, `IG_BUSINESS_ACCOUNT_ID` 두 개 등록

## 8. 60일 토큰 갱신
- long-lived 토큰은 60일마다 갱신 필요 (재발급 or refresh endpoint)
- 만료 임박 알림 세팅 권장 (Meta가 이메일도 보냄)
- 향후 자동 갱신 워크플로 추가 검토 (스코프 밖)

## 테스트 절차
1. `.env`에 두 값 채우고 `python -m src.main render --dry-run` 로컬에서 bootstrap 검증
2. Actions → post → **Run workflow** with `dry_run=true` 로 CI 검증 (이미지 커밋만, IG 호출 없음)
3. `dry_run=false`로 실제 게시 1회 시도
4. cron 자동 실행 대기
