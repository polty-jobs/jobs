from pathlib import Path
from datetime import date

from src.sources.assembly_dataA import AssemblyDataASource

FIX = Path(__file__).parent / "fixtures"


def test_parses_list_with_org_and_title():
    html = (FIX / "assembly_dataA_page1.html").read_bytes()
    src = AssemblyDataASource()
    items = src._parse_list(html)
    assert len(items) > 0
    for it in items:
        assert it.source == "assembly_dataA"
        assert it.category == "국회"
        assert it.org
        assert it.title
        assert it.url.startswith("http")
        assert it.deadline is None  # list view has no deadline column


def test_first_item_matches_known_row():
    """Fixture captured 2026-07-03 — top row is 국회사무처 5497."""
    html = (FIX / "assembly_dataA_page1.html").read_bytes()
    src = AssemblyDataASource()
    items = src._parse_list(html)
    top = items[0]
    assert top.org == "국회사무처"
    assert "관리국 한시임기제공무원" in top.title
    # external_id derived from linkUrl (brd_id-brdi_no)
    assert top.external_id == "001001-5497"
    assert "brdi_no=5497" in top.url


def test_parse_detail_deadline_finds_range():
    synthetic = (
        "<html><body><table><tr><th>접수기간</th>"
        "<td>2026-07-05 ~ 2026-07-12</td></tr></table></body></html>"
    ).encode("utf-8")
    d = AssemblyDataASource._parse_detail_deadline(synthetic)
    assert d == date(2026, 7, 12)


def test_parse_detail_deadline_returns_none_when_absent():
    html = (FIX / "assembly_dataA_detail.html").read_bytes()
    # The captured detail page is JS-rendered — no deadline in static HTML.
    d = AssemblyDataASource._parse_detail_deadline(html)
    assert d is None


def test_fetch_only_hits_list_endpoint(monkeypatch):
    html = (FIX / "assembly_dataA_page1.html").read_bytes()
    src = AssemblyDataASource(max_pages=1)
    hits = []

    class FakeResp:
        content = html
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_get(url, **kw):
        hits.append(url)
        return FakeResp()

    monkeypatch.setattr("src.sources.assembly_dataA.requests.get", fake_get)
    items = src.fetch()
    assert all("dataA.do" in u for u in hits)
    assert len(items) > 0
    assert all(it.deadline is None for it in items)


def test_enrich_with_deadline_falls_back_on_error(monkeypatch):
    from src.sources.base import JobItem
    from datetime import datetime, timezone
    item = JobItem(
        source="assembly_dataA", category="국회", external_id="001001-5497",
        title="t", org="국회사무처", deadline=None,
        url="https://gosi.assembly.go.kr/board/examDetail.do?brd_id=001001&brdi_no=5497",
        fetched_at=datetime.now(timezone.utc),
    )
    def raiser(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr("src.sources.assembly_dataA.requests.get", raiser)
    src = AssemblyDataASource()
    result = src.enrich_with_deadline(item)
    assert result.deadline is None
    assert result.external_id == item.external_id  # unchanged
