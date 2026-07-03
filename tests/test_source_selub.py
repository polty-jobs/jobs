import json
from pathlib import Path
from datetime import date

import pytest

from src.sources.selub import SelubLocalSource

FIX_JSON = Path(__file__).parent / "fixtures" / "selub_local_council_page1.json"


@pytest.fixture
def response_json() -> dict:
    return json.loads(FIX_JSON.read_text(encoding="utf-8"))


def test_parses_all_items_as_지방의회(response_json):
    src = SelubLocalSource()
    items = src._parse(response_json)
    assert len(items) > 0
    for it in items:
        assert it.source == "selub_local"
        assert it.category == "지방의회"
        assert it.external_id  # non-empty string
        assert it.url.startswith("https://www.selub.us/recruit/")


def test_first_item_matches_known_row(response_json):
    """Fixture captured 2026-07-03 — top row is 충주시의회 no=366."""
    src = SelubLocalSource()
    items = src._parse(response_json)
    top = items[0]
    assert top.external_id == "366"
    assert top.org == "충주시의회"
    assert "정책지원관" in top.title
    assert top.url == "https://www.selub.us/recruit/local-council/366"


def test_deadline_parsed_from_subject(response_json):
    src = SelubLocalSource()
    items = src._parse(response_json)
    with_deadline = [i for i in items if i.deadline is not None]
    assert with_deadline
    # First item deadline is 7/15 (from "(~7/15)"); year from createdDate 2026
    assert items[0].deadline == date(2026, 7, 15)


def test_rejects_non_지방의회_response_items():
    """Belt & suspenders: if API returns other-category items by mistake, drop them."""
    payload = {"postList": [
        {"no": 999, "boardCode": "parliamentary", "boardCategoryName": "국회",
         "subject": "[○○의원실] 비서 (~7/10)", "createdDate": "2026-07-03 00:00:00",
         "recruitProgressType": "진행 중"},
        {"no": 1, "boardCode": "local-council", "boardCategoryName": "지방의회",
         "subject": "[서울시의회] 정책보좌관 (~7/12)", "createdDate": "2026-07-03 00:00:00",
         "recruitProgressType": "진행 중"},
    ]}
    src = SelubLocalSource()
    items = src._parse(payload)
    assert [i.external_id for i in items] == ["1"]


def test_skips_fixed_placeholder_posts():
    payload = {"postList": [
        {"no": 42, "boardCode": "local-council", "boardCategoryName": "지방의회",
         "isFixed": True, "recruitProgressType": "-",
         "subject": "공지사항", "createdDate": "2025-01-01 00:00:00"},
        {"no": 43, "boardCode": "local-council", "boardCategoryName": "지방의회",
         "recruitProgressType": "진행 중",
         "subject": "[대구시의회] 6급 (~7/20)", "createdDate": "2026-07-03 00:00:00"},
    ]}
    src = SelubLocalSource()
    items = src._parse(payload)
    assert [i.external_id for i in items] == ["43"]


def test_fetch_posts_to_api(monkeypatch, response_json):
    src = SelubLocalSource()
    calls = []

    class FakeResp:
        status_code = 200

        def json(self):
            return response_json

        def raise_for_status(self):
            pass

    def fake_post(url, **kw):
        calls.append((url, kw.get("data")))
        return FakeResp()

    monkeypatch.setattr("src.sources.selub.requests.post", fake_post)
    items = src.fetch()
    assert len(calls) == 1
    url, body = calls[0]
    assert url == "https://www.selub.us/api/post/get_post_list.sc"
    assert body["boardId"] == "14"
    assert body["recruitProgressType"] == "progress"
    assert len(items) > 0


def test_org_and_title_split_from_subject():
    payload = {"postList": [
        {"no": 100, "boardCode": "local-council", "boardCategoryName": "지방의회",
         "recruitProgressType": "진행 중",
         "subject": "[경기도의회] 정책지원관, 입법조사관 등 (~7/9)",
         "createdDate": "2026-07-03 00:00:00"},
    ]}
    src = SelubLocalSource()
    it = src._parse(payload)[0]
    assert it.org == "경기도의회"
    # Deadline suffix stripped; brackets stripped
    assert "경기도의회" not in it.title
    assert "(~7/9)" not in it.title
    assert "정책지원관" in it.title
