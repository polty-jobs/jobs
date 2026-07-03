from datetime import datetime, timezone
from pathlib import Path
from src.state import State, filter_new
from src.sources.base import JobItem


def _item(source: str, ext_id: str, cat: str = "국회") -> JobItem:
    return JobItem(
        source=source, category=cat, external_id=ext_id,
        title=f"title-{ext_id}", org="org", deadline=None,
        url=f"https://x/{ext_id}", fetched_at=datetime.now(timezone.utc),
    )


def test_load_missing_file_returns_empty(tmp_path: Path):
    st = State.load(tmp_path / "state.json")
    assert st.is_empty()
    assert st.seen == {}


def test_roundtrip_save_load(tmp_path: Path):
    p = tmp_path / "state.json"
    st = State(last_run_at=datetime.now(timezone.utc), seen={"assembly_bbs": ["1", "2"]})
    st.save(p)
    loaded = State.load(p)
    assert loaded.seen == {"assembly_bbs": ["1", "2"]}


def test_filter_new_returns_only_unseen():
    st = State(last_run_at=datetime.now(timezone.utc),
               seen={"assembly_bbs": ["9550", "9551"]})
    items = [_item("assembly_bbs", "9550"), _item("assembly_bbs", "9552")]
    new = filter_new(items, st)
    assert [i.external_id for i in new] == ["9552"]


def test_filter_new_treats_different_sources_independently():
    st = State(last_run_at=datetime.now(timezone.utc),
               seen={"assembly_bbs": ["1"], "assembly_dataA": ["1"]})
    items = [_item("assembly_bbs", "1"), _item("assembly_dataA", "1"),
             _item("selub_local", "1", cat="지방의회")]
    new = filter_new(items, st)
    assert [i.source for i in new] == ["selub_local"]


def test_bootstrap_marks_all_seen_no_new(tmp_path: Path):
    st = State.load(tmp_path / "state.json")
    assert st.is_empty()
    items = [_item("assembly_bbs", "9554"), _item("assembly_bbs", "9553")]
    new = filter_new(items, st, bootstrap_if_empty=True)
    assert new == []
    assert set(st.seen["assembly_bbs"]) == {"9554", "9553"}


def test_record_appends_and_prunes_to_500():
    st = State(last_run_at=datetime.now(timezone.utc),
               seen={"assembly_bbs": [str(i) for i in range(500)]})
    st.record([_item("assembly_bbs", "500"), _item("assembly_bbs", "501")])
    assert len(st.seen["assembly_bbs"]) == 500
    assert "0" not in st.seen["assembly_bbs"]
    assert "1" not in st.seen["assembly_bbs"]
    assert "500" in st.seen["assembly_bbs"]
    assert "501" in st.seen["assembly_bbs"]


def test_record_preserves_insertion_order():
    st = State(last_run_at=datetime.now(timezone.utc), seen={"assembly_bbs": ["1"]})
    st.record([_item("assembly_bbs", "2"), _item("assembly_bbs", "3")])
    assert st.seen["assembly_bbs"] == ["1", "2", "3"]
