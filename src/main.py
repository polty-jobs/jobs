from __future__ import annotations
import argparse
import concurrent.futures
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from src.config import kst_now, session_label as make_session_label, env
from src.instagram import InstagramClient, InstagramError
from src.render import render_digest_png
from src.sources.assembly_bbs import AssemblyBbsSource
from src.sources.assembly_dataA import AssemblyDataASource
from src.sources.selub import SelubLocalSource
from src.sources.base import JobItem
from src.state import State, filter_new

log = logging.getLogger("main")


def _instantiate_sources() -> list:
    return [AssemblyBbsSource(), AssemblyDataASource(), SelubLocalSource()]


def _fetch_all(sources: Sequence) -> tuple[list[JobItem], list[str]]:
    items: list[JobItem] = []
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as ex:
        futures = {ex.submit(s.fetch): s.name for s in sources}
        for fut in concurrent.futures.as_completed(futures):
            name = futures[fut]
            try:
                fetched = fut.result()
                log.info("source %s: %d items", name, len(fetched))
                items.extend(fetched)
            except Exception as e:
                log.warning("source %s failed: %s", name, e)
                failures.append(name)
    return items, failures


def _enrich_deadlines(new_items: list[JobItem]) -> list[JobItem]:
    """Only assembly_dataA needs detail-page fetch. Called for new items only."""
    src = AssemblyDataASource()
    out = []
    for it in new_items:
        if it.source == "assembly_dataA" and it.deadline is None:
            try:
                it = src.enrich_with_deadline(it)
            except Exception as e:
                log.warning("dataA enrich failed for %s: %s", it.external_id, e)
        out.append(it)
    return out


def _item_to_dict(it: JobItem) -> dict:
    return {
        "source": it.source, "category": it.category, "external_id": it.external_id,
        "title": it.title, "org": it.org,
        "deadline": it.deadline.isoformat() if it.deadline else None,
        "url": it.url, "fetched_at": it.fetched_at.isoformat(),
    }


def _item_from_dict(d: dict) -> JobItem:
    return JobItem(
        source=d["source"], category=d["category"], external_id=d["external_id"],
        title=d["title"], org=d["org"],
        deadline=date.fromisoformat(d["deadline"]) if d.get("deadline") else None,
        url=d["url"], fetched_at=datetime.fromisoformat(d["fetched_at"]),
    )


def _summary_counts(items: list[JobItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for it in items:
        counts[it.category] = counts.get(it.category, 0) + 1
    return counts


def _caption(session_label: str, counts: dict[str, int]) -> str:
    parts = []
    if counts.get("국회"):
        parts.append(f"국회 {counts['국회']}건")
    if counts.get("지방의회"):
        parts.append(f"지방의회 {counts['지방의회']}건")
    summary = " · ".join(parts)
    return (
        f"[일일 채용 브리핑 · {session_label}]\n{summary}\n\n"
        "원문 링크는 프로필의 링크트리 참고\n\n"
        "#국회채용 #의원실채용 #지방의회채용 #공공채용"
    )


def cmd_render(
    *,
    state_path: Path,
    posts_dir: Path,
    pending_path: Path,
    session_label: str,
    date_kst: str,
    ig_handle: str,
) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    sources = _instantiate_sources()
    items, failures = _fetch_all(sources)
    if failures and len(failures) == len(sources):
        log.error("all sources failed: %s", failures)
        return 1

    state = State.load(state_path)
    was_empty = state.is_empty()
    new = filter_new(items, state, bootstrap_if_empty=True)

    if was_empty:
        state.last_run_at = kst_now()
        state.save(state_path)
        log.info(
            "bootstrap complete, %d items marked as seen",
            sum(len(v) for v in state.seen.values()),
        )
        pending_path.write_text(json.dumps({"new": [], "png": None}), encoding="utf-8")
        return 0

    if not new:
        log.info("no new items")
        pending_path.write_text(json.dumps({"new": [], "png": None}), encoding="utf-8")
        return 0

    new = _enrich_deadlines(new)

    posts_dir.mkdir(parents=True, exist_ok=True)
    ts_name = kst_now().strftime("%Y-%m-%d-%H%M")
    png_path = posts_dir / f"{ts_name}.png"
    result = render_digest_png(
        new,
        session_label=session_label,
        date_kst=date_kst,
        ig_handle=ig_handle,
        output_path=png_path,
    )
    log.info(
        "rendered %s (%d items; truncated 국회=%d 지방의회=%d)",
        png_path, len(new),
        result.get("truncated_국회", 0),
        result.get("truncated_지방의회", 0),
    )

    pending_path.write_text(json.dumps({
        "new": [_item_to_dict(i) for i in new],
        "png": png_path.name,
        "session_label": session_label,
        "counts": _summary_counts(new),
    }, ensure_ascii=False), encoding="utf-8")
    return 0


def cmd_publish(
    *,
    pending_path: Path,
    state_path: Path,
    ig_business_id: str,
    ig_access_token: str,
    raw_url_base: str,
) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not pending_path.exists():
        log.info("no pending.json — nothing to publish")
        return 0
    data = json.loads(pending_path.read_text(encoding="utf-8"))
    new_dicts = data.get("new") or []
    if not new_dicts:
        log.info("pending.json empty — nothing to publish")
        pending_path.unlink(missing_ok=True)
        return 0

    png_name = data["png"]
    session_label = data["session_label"]
    counts = data["counts"]

    raw_url = f"{raw_url_base.rstrip('/')}/{png_name}"
    caption = _caption(session_label, counts)

    ig = InstagramClient(business_id=ig_business_id, access_token=ig_access_token)
    try:
        post_id = ig.publish_image(image_url=raw_url, caption=caption)
        log.info("IG published: %s", post_id)
    except InstagramError as e:
        log.error("IG publish failed: %s", e)
        return 1  # keep pending.json for retry

    new_items = [_item_from_dict(d) for d in new_dicts]
    state = State.load(state_path)
    state.record(new_items)
    state.last_run_at = kst_now()
    state.save(state_path)
    log.info("state updated with %d new items", len(new_items))

    pending_path.unlink(missing_ok=True)
    return 0


def _cli() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render")
    r.add_argument("--state", default="state.json")
    r.add_argument("--posts-dir", default="posts")
    r.add_argument("--pending", default="pending.json")

    pub = sub.add_parser("publish")
    pub.add_argument("--pending", default="pending.json")
    pub.add_argument("--state", default="state.json")
    pub.add_argument("--raw-url-base", required=True)

    args = p.parse_args()

    if args.cmd == "render":
        now = kst_now()
        return cmd_render(
            state_path=Path(args.state),
            posts_dir=Path(args.posts_dir),
            pending_path=Path(args.pending),
            session_label=make_session_label(now),
            date_kst=now.strftime("%Y-%m-%d"),
            ig_handle=env("IG_HANDLE", "polty.jobs"),
        )
    if args.cmd == "publish":
        return cmd_publish(
            pending_path=Path(args.pending),
            state_path=Path(args.state),
            ig_business_id=env("IG_BUSINESS_ACCOUNT_ID", required=True),
            ig_access_token=env("IG_ACCESS_TOKEN", required=True),
            raw_url_base=args.raw_url_base,
        )
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
