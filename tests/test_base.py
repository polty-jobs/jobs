from datetime import date, datetime, timezone
import pytest
from src.sources.base import JobItem


def test_dedup_key_combines_source_and_id():
    item = JobItem(
        source="assembly_bbs",
        category="국회",
        external_id="9554",
        title="○○○의원실 6급 비서 채용",
        org="○○○의원실",
        deadline=date(2026, 7, 10),
        url="https://assembly.go.kr/...",
        fetched_at=datetime.now(timezone.utc),
    )
    assert item.dedup_key() == "assembly_bbs:9554"


def test_jobitem_is_hashable_and_frozen():
    item = JobItem(
        source="s", category="국회", external_id="1", title="t",
        org="o", deadline=None, url="u", fetched_at=datetime.now(timezone.utc)
    )
    with pytest.raises(Exception):
        item.title = "changed"  # frozen dataclass
    hash(item)


def test_category_must_be_valid():
    with pytest.raises(ValueError, match="category"):
        JobItem(
            source="s", category="이상한거", external_id="1", title="t",
            org="o", deadline=None, url="u", fetched_at=datetime.now(timezone.utc),
        )
