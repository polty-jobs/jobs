from __future__ import annotations
import re
import time
from dataclasses import replace
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from src.sources.base import JobItem

LIST_URL = "https://assembly.go.kr/portal/cnts/cntsCont/dataA.do"
BASE = "https://assembly.go.kr"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) polty-jobs-bot"

_DATE_RE = re.compile(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})")


class AssemblyDataASource:
    name = "assembly_dataA"
    category = "국회"

    def __init__(self, per_page: int = 10, max_pages: int = 2) -> None:
        self.per_page = per_page
        self.max_pages = max_pages

    def fetch(self) -> list[JobItem]:
        items: list[JobItem] = []
        for page in range(1, self.max_pages + 1):
            params = {
                "menuNo": "600107",
                "cntsDivCd": "JOB",
                "pageIndex": str(page),
            }
            resp = requests.get(
                LIST_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            page_items = self._parse_list(resp.content)
            items.extend(page_items)
            if len(page_items) < self.per_page:
                break
            time.sleep(1)
        return items

    def enrich_with_deadline(self, item: JobItem) -> JobItem:
        """Try to fetch detail page and parse a deadline; return item unchanged on failure."""
        try:
            resp = requests.get(
                item.url,
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            deadline = self._parse_detail_deadline(resp.content)
            if deadline is None:
                return item
            return replace(item, deadline=deadline)
        except Exception:
            return item

    def _parse_list(self, html: bytes | str) -> list[JobItem]:
        soup = BeautifulSoup(html, "lxml")
        table = self._find_list_table(soup)
        if table is None:
            raise RuntimeError(
                "assembly_dataA: list table not found — page structure changed?"
            )

        now = datetime.now(timezone.utc)
        items: list[JobItem] = []
        tbody = table.find("tbody")
        if tbody is None:
            return items

        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue

            row_num = cells[0].get_text(strip=True)
            if not row_num.isdigit():
                continue

            org = cells[1].get_text(" ", strip=True)
            title_cell = cells[2]

            # Detail URL is stashed in a hidden input.linkUrl, not the anchor.
            link_input = title_cell.find("input", {"id": "linkUrl"}) or title_cell.find(
                "input", {"name": "linkUrl"}
            )
            if not link_input or not link_input.get("value"):
                continue
            url = link_input["value"]

            title_a = title_cell.find("a") or title_cell
            title = title_a.get_text(" ", strip=True)

            external_id = self._external_id_from_url(url)
            items.append(JobItem(
                source=self.name,
                category=self.category,
                external_id=external_id,
                title=title,
                org=org,
                deadline=None,  # populated later by enrich_with_deadline
                url=url,
                fetched_at=now,
            ))
        return items

    @staticmethod
    def _find_list_table(soup: BeautifulSoup):
        for t in soup.find_all("table"):
            thead = t.find("thead")
            if not thead:
                continue
            headers = [th.get_text(strip=True) for th in thead.find_all("th")]
            if set(headers) >= {"번호", "소속기관명", "제목", "작성일자"}:
                return t
        return None

    @staticmethod
    def _external_id_from_url(url: str) -> str:
        """Stable identifier: '{brd_id}-{brdi_no}' when present, else the URL itself."""
        try:
            q = parse_qs(urlparse(url).query)
            brd_id = q.get("brd_id", [None])[0]
            brdi_no = q.get("brdi_no", [None])[0]
            if brd_id and brdi_no:
                return f"{brd_id}-{brdi_no}"
        except Exception:
            pass
        return url

    @staticmethod
    def _parse_detail_deadline(html: bytes | str) -> date | None:
        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        # Prefer "접수기간 YYYY-MM-DD ~ YYYY-MM-DD" (use second date).
        m = re.search(
            r"(?:접수기간|접수\s*기간|공고기간|공고\s*기간|기간)"
            r"[^0-9]{0,10}"
            r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})"
            r"[^0-9]+(\d{4})[-.](\d{1,2})[-.](\d{1,2})",
            text,
        )
        if m:
            y, mo, d = m.group(4), m.group(5), m.group(6)
            try:
                return date(int(y), int(mo), int(d))
            except ValueError:
                return None
        # Fallback: "마감 YYYY-MM-DD" or "마감일 YYYY-MM-DD"
        m = re.search(
            r"마감(?:일)?[^0-9]{0,10}(\d{4})[-.](\d{1,2})[-.](\d{1,2})",
            text,
        )
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
        return None
