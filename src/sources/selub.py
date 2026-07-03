from __future__ import annotations
import re
from datetime import date, datetime, timezone

import requests

from src.sources.base import JobItem

API_URL = "https://www.selub.us/api/post/get_post_list.sc"
BASE = "https://www.selub.us"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) polty-jobs-bot"

LOCAL_COUNCIL_BOARD_ID = "14"

# Subject formats:
#   "[충주시의회] 정책지원관(일반임기제 7급) (~7/15)"
#   "[경기도의회] 정책지원관, 입법조사관 등 (~7/9)"
_ORG_RE = re.compile(r"^\s*\[([^\]]+)\]\s*")
_DEADLINE_RE = re.compile(r"\(~\s*(\d{1,2})[/.\-](\d{1,2})\s*\)")


class SelubLocalSource:
    name = "selub_local"
    category = "지방의회"

    def __init__(self, per_page: int = 20, max_pages: int = 2) -> None:
        self.per_page = per_page
        self.max_pages = max_pages

    def fetch(self) -> list[JobItem]:
        all_items: list[JobItem] = []
        for page in range(1, self.max_pages + 1):
            resp = requests.post(
                API_URL,
                data={
                    "boardType": "recruit",
                    "boardId": LOCAL_COUNCIL_BOARD_ID,
                    "page": str(page),
                    "listType": "text",
                    "recruitProgressType": "progress",
                },
                headers={
                    "User-Agent": USER_AGENT,
                    "x-requested-with": "XMLHttpRequest",
                    "referer": f"{BASE}/recruit/all",
                    "accept": "application/json, text/javascript, */*; q=0.01",
                },
                timeout=15,
            )
            resp.raise_for_status()
            page_items = self._parse(resp.json())
            all_items.extend(page_items)
            if len(page_items) < self.per_page:
                break
        return all_items

    def _parse(self, payload: dict) -> list[JobItem]:
        posts = payload.get("postList")
        if posts is None:
            raise RuntimeError(
                "selub_local: response has no 'postList' — API contract changed?"
            )

        now_utc = datetime.now(timezone.utc)
        items: list[JobItem] = []
        for post in posts:
            # Category scope — only 지방의회 items are emitted.
            if post.get("boardCode") != "local-council" and post.get("boardCategoryName") != "지방의회":
                continue
            # Skip pinned announcements/placeholder posts.
            if post.get("recruitProgressType") != "진행 중":
                continue

            subject_raw = post.get("subject") or ""
            org, title = self._split_subject(subject_raw)
            if not title:
                continue

            no = post.get("no")
            if no is None:
                continue

            created = post.get("createdDate") or ""
            deadline = self._parse_deadline(subject_raw, created)
            url = f"{BASE}/recruit/local-council/{no}"

            items.append(JobItem(
                source=self.name,
                category=self.category,
                external_id=str(no),
                title=title,
                org=org,
                deadline=deadline,
                url=url,
                fetched_at=now_utc,
            ))
        return items

    @staticmethod
    def _split_subject(subject: str) -> tuple[str, str]:
        """Split '[의회명] 직책 (~M/D)' into (org, title_without_prefix_and_deadline)."""
        m = _ORG_RE.match(subject)
        if m:
            org = m.group(1).strip()
            remainder = subject[m.end():]
        else:
            org = ""
            remainder = subject
        # strip deadline suffix
        title = _DEADLINE_RE.sub("", remainder).strip()
        # tidy trailing punctuation
        title = re.sub(r"\s+", " ", title).strip(" ·-")
        return org, title

    @staticmethod
    def _parse_deadline(subject: str, created_date_str: str) -> date | None:
        m = _DEADLINE_RE.search(subject)
        if not m:
            return None
        month, day = int(m.group(1)), int(m.group(2))
        year = _year_from(created_date_str)
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        # If deadline appears earlier than created date, bump to next year.
        created = _date_from(created_date_str)
        if created and d < created:
            try:
                d = date(year + 1, month, day)
            except ValueError:
                return None
        return d


def _year_from(created_date_str: str) -> int:
    if len(created_date_str) >= 4 and created_date_str[:4].isdigit():
        return int(created_date_str[:4])
    return datetime.now(timezone.utc).year


def _date_from(created_date_str: str) -> date | None:
    try:
        return datetime.strptime(created_date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
