import json
from datetime import datetime, timezone
from pathlib import Path

from src.main import cmd_mark_seen


def _pending_dict(external_id: str) -> dict:
    return {
        "source": "assembly_bbs", "category": "국회",
        "external_id": external_id, "title": "t", "org": "o",
        "deadline": None, "url": "https://x",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def test_mark_seen_records_and_deletes_pending(tmp_path: Path):
    state_p = tmp_path / "state.json"
    pending_p = tmp_path / "pending.json"
    state_p.write_text(
        '{"version":1,"last_run_at":null,"seen":{"assembly_bbs":["1"]}}'
    )
    pending_p.write_text(json.dumps({
        "new": [_pending_dict("2"), _pending_dict("3")],
        "png": "img.png",
        "session_label": "AM 10시",
        "counts": {"국회": 2},
    }))

    rc = cmd_mark_seen(pending_path=pending_p, state_path=state_p)
    assert rc == 0

    state = json.loads(state_p.read_text())
    assert set(state["seen"]["assembly_bbs"]) == {"1", "2", "3"}
    assert not pending_p.exists()


def test_mark_seen_empty_pending_is_noop(tmp_path: Path):
    state_p = tmp_path / "state.json"
    pending_p = tmp_path / "pending.json"
    state_p.write_text('{"version":1,"last_run_at":null,"seen":{}}')
    pending_p.write_text('{"new":[],"png":null}')

    rc = cmd_mark_seen(pending_path=pending_p, state_path=state_p)
    assert rc == 0
    assert not pending_p.exists()
    state = json.loads(state_p.read_text())
    assert state["seen"] == {}


def test_mark_seen_missing_pending_is_noop(tmp_path: Path):
    state_p = tmp_path / "state.json"
    state_p.write_text('{"version":1,"last_run_at":null,"seen":{"a":["1"]}}')
    rc = cmd_mark_seen(
        pending_path=tmp_path / "pending.json",
        state_path=state_p,
    )
    assert rc == 0
