from __future__ import annotations
import re
import time
from datetime import date, datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base import JobItem

LIST_URL = "https://assembly.go.kr/portal/bbs/B0000038/list.do"
BASE = "https://assembly.go.kr"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) polty-jobs-bot"

_DATE_RE = re.compile(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})")


class AssemblyBbsSource:
    name = "assembly_bbs"
    category = "국회"

    def __init__(self, per_page: int = 10, max_pages: int = 2) -> None:
        self.per_page = per_page
        self.max_pages = max_pages

    def fetch(self) -> list[JobItem]:
        all_items: list[JobItem] = []
        for page in range(1, self.max_pages + 1):
            params = {
                "menuNo": "600097",
                "sttus": "진행중",
                "pageIndex": str(page),
            }
            resp = requests.get(
                LIST_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=(30, 60),  # (connect, read) — GitHub Actions runners hit assembly.go.kr slowly
            )
            resp.raise_for_status()
            page_items = self._parse(resp.content)
            all_items.extend(page_items)
            if len(page_items) < self.per_page:
                break
            time.sleep(1)
        return all_items

    def _parse(self, html: bytes | str) -> list[JobItem]:
        soup = BeautifulSoup(html, "lxml")
        table = self._find_recruit_table(soup)
        if table is None:
            raise RuntimeError(
                "assembly_bbs: recruitment table not found — page structure changed?"
            )

        now = datetime.now(timezone.utc)
        items: list[JobItem] = []
        tbody = table.find("tbody")
        if tbody is None:
            return items

        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            # Expected columns: [번호] [상태] [제목] [기간] [담당부서] [작성일] [조회]
            if len(cells) < 5:
                continue

            external_id = cells[0].get_text(strip=True)
            if not external_id.isdigit():
                continue

            # Server-side sttus=진행중 already filters, but keep a soft check
            # against "마감" so we can defend if the filter param is ignored.
            state = cells[1].get_text(strip=True)
            if state and "마감" in state:
                continue

            title_a = cells[2].find("a", class_="board_subject") or cells[2].find("a")
            if not title_a:
                continue
            title = title_a.get_text(" ", strip=True)
            href = title_a.get("href", "")
            url = urljoin(BASE, href)

            period = cells[3].get_text(" ", strip=True)
            deadline = self._parse_deadline(period)

            org = cells[4].get_text(" ", strip=True)

            items.append(JobItem(
                source=self.name,
                category=self.category,
                external_id=external_id,
                title=title,
                org=org,
                deadline=deadline,
                url=url,
                fetched_at=now,
            ))
        return items

    @staticmethod
    def _find_recruit_table(soup: BeautifulSoup):
        # Match table whose thead has a known column set. Robust to layout shifts.
        for t in soup.find_all("table"):
            thead = t.find("thead")
            if not thead:
                continue
            headers = [th.get_text(strip=True) for th in thead.find_all("th")]
            if set(headers) >= {"번호", "상태", "제목", "기간", "담당부서"}:
                return t
        return None

    @staticmethod
    def _parse_deadline(period: str) -> date | None:
        matches = _DATE_RE.findall(period)
        if len(matches) >= 2:
            y, mo, d = matches[-1]
        elif len(matches) == 1:
            y, mo, d = matches[0]
        else:
            return None
        try:
            return date(int(y), int(mo), int(d))
        except ValueError:
            return None
