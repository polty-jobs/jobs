from datetime import date, datetime, timezone
from pathlib import Path
import pytest

from src.render import render_digest_html, render_digest_png
from src.sources.base import JobItem


def _item(cat: str, ext: str, title: str = "타이틀", org: str = "조직",
          deadline: date | None = date(2026, 7, 10)) -> JobItem:
    return JobItem(source="s", category=cat, external_id=ext, title=title,
                   org=org, deadline=deadline,
                   url="https://x", fetched_at=datetime.now(timezone.utc))


def test_html_contains_both_categories_when_both_have_items():
    items = [_item("국회", "1", org="○○○의원실", title="비서 채용"),
             _item("지방의회", "2", org="서울시의회", title="정책보좌관")]
    html = render_digest_html(items, session_label="AM 10시",
                              date_kst="2026-07-03", ig_handle="polty.jobs")
    assert "국회" in html and "지방의회" in html
    assert "비서 채용" in html and "정책보좌관" in html
    assert "@polty.jobs" in html


def test_html_omits_empty_category_section():
    items = [_item("국회", "1")]
    html = render_digest_html(items, session_label="AM 10시",
                              date_kst="2026-07-03", ig_handle="x")
    assert '>국회<' in html
    assert '>지방의회<' not in html


def test_html_size_class_scales_with_count():
    items_small = [_item("국회", str(i)) for i in range(5)]
    items_large = [_item("국회", str(i)) for i in range(25)]
    assert 'sz-1' in render_digest_html(items_small, session_label="AM 10시",
                                        date_kst="2026-07-03", ig_handle="x")
    assert 'sz-3' in render_digest_html(items_large, session_label="AM 10시",
                                        date_kst="2026-07-03", ig_handle="x")


def test_deadline_shortdate_formatting():
    items = [_item("국회", "1", deadline=date(2026, 7, 5))]
    html = render_digest_html(items, session_label="AM 10시",
                              date_kst="2026-07-03", ig_handle="x")
    assert "~7/5" in html


def test_deadline_missing_is_omitted():
    items = [_item("국회", "1", deadline=None)]
    html = render_digest_html(items, session_label="AM 10시",
                              date_kst="2026-07-03", ig_handle="x")
    # No " · ~" trailing on the li line
    assert "~" not in html.split("<footer")[0]


@pytest.mark.slow
def test_png_output_dimensions(tmp_path: Path):
    items = [_item("국회", "1")]
    out = tmp_path / "test.png"
    render_digest_png(items, session_label="AM 10시", date_kst="2026-07-03",
                      ig_handle="x", output_path=out)
    assert out.exists()
    from PIL import Image
    with Image.open(out) as im:
        assert im.size == (1080, 1350)


@pytest.mark.slow
def test_truncation_when_overflow_detected(tmp_path: Path):
    """60+ long items should trigger truncation."""
    items = [_item("국회", str(i),
                   title=f"매우 매우 매우 매우 긴 채용공고 제목 번호 {i}",
                   org=f"○○○의원실{i}")
             for i in range(60)]
    out = tmp_path / "overflow.png"
    result = render_digest_png(items, session_label="AM 10시",
                               date_kst="2026-07-03", ig_handle="x",
                               output_path=out)
    assert out.exists()
    assert result["truncated_국회"] > 0, "expected truncation to kick in for 60-item flood"
