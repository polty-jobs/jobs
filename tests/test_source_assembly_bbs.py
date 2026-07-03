from pathlib import Path
from datetime import date
import pytest

from src.sources.assembly_bbs import AssemblyBbsSource

FIXTURE = Path(__file__).parent / "fixtures" / "assembly_bbs_page1.html"


@pytest.fixture
def html_bytes() -> bytes:
    return FIXTURE.read_bytes()


def test_parses_active_items_only(html_bytes):
    src = AssemblyBbsSource()
    items = src._parse(html_bytes)
    assert len(items) > 0
    for it in items:
        assert it.source == "assembly_bbs"
        assert it.category == "국회"
        assert it.external_id.isdigit()
        assert it.title
        assert it.org
        assert it.url.startswith("https://assembly.go.kr")


def test_first_item_matches_known_row(html_bytes):
    """Fixture captured 2026-07-03 — top row is nttId=4781147, 이상식 의원실."""
    src = AssemblyBbsSource()
    items = src._parse(html_bytes)
    top = items[0]
    assert top.external_id == "9554"
    assert "이상식" in top.title
    assert top.org == "이상식의원실"
    assert "nttId=4781147" in top.url


def test_deadline_parsed_from_period(html_bytes):
    src = AssemblyBbsSource()
    items = src._parse(html_bytes)
    with_deadline = [i for i in items if i.deadline is not None]
    assert with_deadline
    for it in with_deadline:
        assert isinstance(it.deadline, date)
    # First row deadline is 2026-07-12
    assert items[0].deadline == date(2026, 7, 12)


def test_fetch_uses_http_and_calls_list_url(monkeypatch, html_bytes):
    src = AssemblyBbsSource(max_pages=1)
    calls = []

    class FakeResp:
        content = html_bytes
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_get(url, **kw):
        calls.append((url, kw.get("params", {})))
        return FakeResp()

    monkeypatch.setattr("src.sources.assembly_bbs.requests.get", fake_get)
    items = src.fetch()
    assert calls, "expected at least one HTTP call"
    assert "list.do" in calls[0][0]
    assert len(items) > 0
