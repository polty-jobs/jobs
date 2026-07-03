import json
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock

from src.main import cmd_render, cmd_publish
from src.sources.base import JobItem


def _item(source: str, ext: str, cat: str = "국회") -> JobItem:
    return JobItem(source=source, category=cat, external_id=ext,
                   title=f"t-{ext}", org="o", deadline=date(2026, 7, 10),
                   url=f"https://x/{ext}", fetched_at=datetime.now(timezone.utc))


def _setup(tmp_path):
    posts_dir = tmp_path / "posts"; posts_dir.mkdir()
    return tmp_path / "state.json", posts_dir, tmp_path / "pending.json"


def test_render_bootstrap_populates_state_and_writes_empty_pending(tmp_path):
    state_p, posts, pending_p = _setup(tmp_path)
    with patch("src.main._instantiate_sources") as srcs, \
         patch("src.main.render_digest_png") as rend:
        s = MagicMock(); s.name = "assembly_bbs"
        s.fetch.return_value = [_item("assembly_bbs", "9560"), _item("assembly_bbs", "9561")]
        srcs.return_value = [s]
        rc = cmd_render(state_path=state_p, posts_dir=posts, pending_path=pending_p,
                        session_label="AM 10시", date_kst="2026-07-03", ig_handle="x")
        assert rc == 0
        rend.assert_not_called()
        state = json.loads(state_p.read_text())
        assert set(state["seen"]["assembly_bbs"]) == {"9560", "9561"}
        pending = json.loads(pending_p.read_text())
        assert pending["new"] == [] and pending["png"] is None


def test_render_no_new_items_writes_empty_pending(tmp_path):
    state_p, posts, pending_p = _setup(tmp_path)
    state_p.write_text('{"version":1,"last_run_at":null,"seen":{"assembly_bbs":["1"]}}')
    with patch("src.main._instantiate_sources") as srcs, \
         patch("src.main.render_digest_png") as rend:
        s = MagicMock(); s.name = "assembly_bbs"
        s.fetch.return_value = [_item("assembly_bbs", "1")]
        srcs.return_value = [s]
        rc = cmd_render(state_path=state_p, posts_dir=posts, pending_path=pending_p,
                        session_label="AM 10시", date_kst="2026-07-03", ig_handle="x")
        assert rc == 0
        rend.assert_not_called()
        pending = json.loads(pending_p.read_text())
        assert pending["new"] == []


def test_render_with_new_items_writes_pending_and_renders(tmp_path):
    state_p, posts, pending_p = _setup(tmp_path)
    state_p.write_text('{"version":1,"last_run_at":null,"seen":{"assembly_bbs":["1"]}}')
    with patch("src.main._instantiate_sources") as srcs, \
         patch("src.main.render_digest_png") as rend:
        s = MagicMock(); s.name = "assembly_bbs"
        s.fetch.return_value = [_item("assembly_bbs", "1"), _item("assembly_bbs", "2")]
        srcs.return_value = [s]
        rend.return_value = {"truncated_국회": 0, "truncated_지방의회": 0}
        rc = cmd_render(state_path=state_p, posts_dir=posts, pending_path=pending_p,
                        session_label="AM 10시", date_kst="2026-07-03", ig_handle="x")
        assert rc == 0
        rend.assert_called_once()
        pending = json.loads(pending_p.read_text())
        assert len(pending["new"]) == 1
        assert pending["new"][0]["external_id"] == "2"
        assert pending["png"].endswith(".png")


def test_render_single_source_failure_does_not_abort(tmp_path):
    state_p, posts, pending_p = _setup(tmp_path)
    state_p.write_text('{"version":1,"last_run_at":null,"seen":{"assembly_bbs":["0"]}}')
    with patch("src.main._instantiate_sources") as srcs, \
         patch("src.main.render_digest_png") as rend:
        good = MagicMock(); good.name = "assembly_bbs"
        good.fetch.return_value = [_item("assembly_bbs", "9560")]
        bad = MagicMock(); bad.name = "selub_local"
        bad.fetch.side_effect = RuntimeError("boom")
        srcs.return_value = [good, bad]
        rend.return_value = {"truncated_국회": 0, "truncated_지방의회": 0}
        rc = cmd_render(state_path=state_p, posts_dir=posts, pending_path=pending_p,
                        session_label="AM 10시", date_kst="2026-07-03", ig_handle="x")
        assert rc == 0
        rend.assert_called_once()


def test_render_all_sources_failed_returns_1(tmp_path):
    state_p, posts, pending_p = _setup(tmp_path)
    with patch("src.main._instantiate_sources") as srcs:
        s = MagicMock(); s.name = "s"; s.fetch.side_effect = RuntimeError("x")
        srcs.return_value = [s]
        rc = cmd_render(state_path=state_p, posts_dir=posts, pending_path=pending_p,
                        session_label="AM 10시", date_kst="2026-07-03", ig_handle="x")
        assert rc == 1


def test_publish_empty_pending_is_noop(tmp_path):
    state_p, posts, pending_p = _setup(tmp_path)
    state_p.write_text('{"version":1,"last_run_at":null,"seen":{}}')
    pending_p.write_text('{"new":[],"png":null}')
    with patch("src.main.InstagramClient") as IG:
        rc = cmd_publish(pending_path=pending_p, state_path=state_p,
                         ig_business_id="B", ig_access_token="T",
                         raw_url_base="https://raw/x")
        assert rc == 0
        IG.assert_not_called()
        assert not pending_p.exists()


def test_publish_uploads_and_updates_state(tmp_path):
    state_p, posts, pending_p = _setup(tmp_path)
    state_p.write_text('{"version":1,"last_run_at":null,"seen":{"assembly_bbs":["0"]}}')
    pending_p.write_text(json.dumps({
        "new": [{
            "source": "assembly_bbs", "category": "국회", "external_id": "9560",
            "title": "t", "org": "o", "deadline": "2026-07-10",
            "url": "https://x/9560",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }],
        "png": "2026-07-03-1000.png",
        "session_label": "AM 10시",
        "counts": {"국회": 1},
    }, ensure_ascii=False))
    with patch("src.main.InstagramClient") as IG:
        client = MagicMock(); client.publish_image.return_value = "POST_1"
        IG.return_value = client
        rc = cmd_publish(pending_path=pending_p, state_path=state_p,
                         ig_business_id="B", ig_access_token="T",
                         raw_url_base="https://raw.githubusercontent.com/u/r/main/posts")
        assert rc == 0
        client.publish_image.assert_called_once()
        _, kwargs = client.publish_image.call_args
        assert kwargs["image_url"] == "https://raw.githubusercontent.com/u/r/main/posts/2026-07-03-1000.png"
        state = json.loads(state_p.read_text())
        assert "9560" in state["seen"]["assembly_bbs"]
        assert not pending_p.exists()


def test_publish_ig_failure_returns_1_and_keeps_pending(tmp_path):
    from src.instagram import InstagramError
    state_p, posts, pending_p = _setup(tmp_path)
    state_p.write_text('{"version":1,"last_run_at":null,"seen":{}}')
    pending_p.write_text(json.dumps({
        "new": [{"source":"s","category":"국회","external_id":"1","title":"t","org":"o",
                 "deadline":None,"url":"https://x","fetched_at":datetime.now(timezone.utc).isoformat()}],
        "png": "x.png", "session_label": "AM 10시", "counts": {"국회": 1},
    }))
    with patch("src.main.InstagramClient") as IG:
        client = MagicMock(); client.publish_image.side_effect = InstagramError("nope")
        IG.return_value = client
        rc = cmd_publish(pending_path=pending_p, state_path=state_p,
                         ig_business_id="B", ig_access_token="T",
                         raw_url_base="https://raw/x")
        assert rc == 1
        assert pending_p.exists()
