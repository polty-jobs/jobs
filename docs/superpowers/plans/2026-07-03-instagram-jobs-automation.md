# Instagram Jobs Automation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate a twice-daily Instagram digest of new job postings from three Korean political/public-sector recruitment sources (국회 의원실채용, 국회 국회채용, 셀럽어스 지방의회).

**Architecture:** Python 3.11+ orchestrator runs on GitHub Actions cron (UTC 01:00 / 09:00 = KST 10:00 / 18:00). Fetches sources in parallel, dedupes against `state.json`, renders an HTML/CSS digest via Playwright screenshot (1080×1350 PNG), commits the PNG to `posts/`, then publishes via Instagram Graph API (2-step: container → publish). State is committed back to the repo after successful upload.

**Tech Stack:** Python 3.11, `requests`, `beautifulsoup4`, `playwright` (Chromium), `jinja2`, `pytest`, GitHub Actions.

**Spec reference:** `docs/superpowers/specs/2026-07-03-instagram-jobs-automation-design.md`

**TDD discipline (all tasks):** Write failing test → run and confirm failure message → implement minimum → run to green → refactor if needed → commit.

**Skills to invoke during execution:**
- @superpowers:test-driven-development for every source/parser/logic task
- @superpowers:verification-before-completion before marking any task complete
- @superpowers:systematic-debugging when a test won't pass

---

## Task 0: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/sources/__init__.py`
- Create: `src/templates/.gitkeep`
- Create: `tests/__init__.py`
- Create: `tests/fixtures/.gitkeep`
- Create: `tests/snapshots/.gitkeep`
- Create: `posts/.gitkeep`
- Modify: `.gitignore` (already has base, no change needed)

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "polty-jobs"
version = "0.1.0"
description = "Automated Instagram digest of political sector jobs"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "lxml>=5.1",
    "playwright>=1.44",
    "jinja2>=3.1",
    "python-dateutil>=2.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "responses>=0.25",
    "ruff>=0.4",
    "pixelmatch>=0.3",
    "pillow>=10.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Write `requirements.txt`** (for GitHub Actions convenience)

```
requests>=2.31
beautifulsoup4>=4.12
lxml>=5.1
playwright>=1.44
jinja2>=3.1
python-dateutil>=2.9
```

- [ ] **Step 3: Write `.env.example`**

```
# Instagram Graph API — get these from Meta for Developers
IG_ACCESS_TOKEN=EAA...
IG_BUSINESS_ACCOUNT_ID=178414...

# Optional: Slack failure notifications
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Optional: repo owner/name used to build raw URL (auto-detected from git in CI)
# GIT_REPO_OWNER=polty-jobs
# GIT_REPO_NAME=jobs
```

- [ ] **Step 4: Create empty package/test dirs**

```bash
mkdir -p src/sources src/templates tests/fixtures tests/snapshots posts
touch src/__init__.py src/sources/__init__.py tests/__init__.py
touch src/templates/.gitkeep tests/fixtures/.gitkeep tests/snapshots/.gitkeep posts/.gitkeep
```

- [ ] **Step 5: Local venv + install (developer convenience — CI installs separately)**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m playwright install chromium
```

- [ ] **Step 6: Sanity — `pytest` should collect 0 tests without error**

Run: `pytest`
Expected: `no tests ran` (exit 5), no import errors.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml requirements.txt .env.example src/ tests/ posts/
git commit -m "chore: scaffold Python project structure"
```

---

## Task 1: Data Model — `JobItem` and `Source` Protocol

**Files:**
- Create: `src/sources/base.py`
- Test: `tests/test_base.py`

- [ ] **Step 1: Write failing test `tests/test_base.py`**

```python
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
    # Should be hashable (frozen=True implies hashable when eq=True default)
    hash(item)


def test_category_must_be_valid():
    with pytest.raises(ValueError, match="category"):
        JobItem(
            source="s", category="이상한거", external_id="1", title="t",
            org="o", deadline=None, url="u", fetched_at=datetime.now(timezone.utc),
        )
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/test_base.py -x`
Expected: `ImportError: cannot import name 'JobItem'`

- [ ] **Step 3: Implement `src/sources/base.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

VALID_CATEGORIES = {"국회", "지방의회"}


@dataclass(frozen=True)
class JobItem:
    source: str
    category: str
    external_id: str
    title: str
    org: str
    deadline: date | None
    url: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {VALID_CATEGORIES}, got {self.category!r}")

    def dedup_key(self) -> str:
        return f"{self.source}:{self.external_id}"


class Source(Protocol):
    name: str      # dedup key prefix, e.g. "assembly_bbs"
    category: str  # "국회" or "지방의회"

    def fetch(self) -> list[JobItem]:
        """Fetch active job postings. Raises on network/parse failure."""
        ...
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_base.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/sources/base.py tests/test_base.py
git commit -m "feat: define JobItem data model and Source protocol"
```

---

## Task 2: State Management (`state.json` + dedup)

**Files:**
- Create: `src/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing test `tests/test_state.py`**

```python
import json
from datetime import date, datetime, timezone
from pathlib import Path
import pytest
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
    """First run: all items go to seen, none returned as new."""
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
    # oldest pruned (FIFO)
    assert "0" not in st.seen["assembly_bbs"]
    assert "1" not in st.seen["assembly_bbs"]
    assert "500" in st.seen["assembly_bbs"]
    assert "501" in st.seen["assembly_bbs"]


def test_record_preserves_insertion_order():
    st = State(last_run_at=datetime.now(timezone.utc), seen={"assembly_bbs": ["1"]})
    st.record([_item("assembly_bbs", "2"), _item("assembly_bbs", "3")])
    assert st.seen["assembly_bbs"] == ["1", "2", "3"]
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/test_state.py -x`
Expected: `ImportError`.

- [ ] **Step 3: Implement `src/state.py`**

```python
from __future__ import annotations
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.sources.base import JobItem

MAX_SEEN_PER_SOURCE = 500


@dataclass
class State:
    last_run_at: datetime | None
    seen: dict[str, list[str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any(self.seen.values())

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls(last_run_at=None, seen={})
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            last_run_at=datetime.fromisoformat(raw["last_run_at"]) if raw.get("last_run_at") else None,
            seen={k: list(v) for k, v in raw.get("seen", {}).items()},
        )

    def save(self, path: Path) -> None:
        payload = {
            "version": 1,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "seen": self.seen,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(self, items: list[JobItem]) -> None:
        """Append external_ids to seen, prune to MAX_SEEN_PER_SOURCE (FIFO)."""
        by_source: dict[str, list[str]] = {}
        for it in items:
            by_source.setdefault(it.source, []).append(it.external_id)
        for source, ids in by_source.items():
            existing = self.seen.setdefault(source, [])
            # dedup within existing (preserve order)
            for new_id in ids:
                if new_id not in existing:
                    existing.append(new_id)
            # prune FIFO
            if len(existing) > MAX_SEEN_PER_SOURCE:
                del existing[: len(existing) - MAX_SEEN_PER_SOURCE]


def filter_new(items: list[JobItem], state: State, bootstrap_if_empty: bool = False) -> list[JobItem]:
    """Return items whose (source, external_id) is not in state.

    If bootstrap_if_empty and state is empty, record everything and return [].
    """
    if bootstrap_if_empty and state.is_empty():
        state.record(items)
        return []
    new = []
    for it in items:
        if it.external_id not in state.seen.get(it.source, []):
            new.append(it)
    return new
```

- [ ] **Step 4: Run tests — PASS**

Run: `pytest tests/test_state.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/state.py tests/test_state.py
git commit -m "feat: state persistence, dedup filter, FIFO prune"
```

---

## Task 3: Source — `assembly_bbs` (국회 의원실채용)

**Files:**
- Create: `src/sources/assembly_bbs.py`
- Create: `tests/fixtures/assembly_bbs_page1.html` (real page snapshot)
- Test: `tests/test_source_assembly_bbs.py`

**Discovery preface — do this first, then commit fixture separately:**

- [ ] **Step 0: Capture live HTML fixture**

```bash
mkdir -p tests/fixtures
curl -sL 'https://assembly.go.kr/portal/bbs/B0000038/list.do?menuNo=600097' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' \
  > tests/fixtures/assembly_bbs_page1.html
```

Inspect the file. Confirm the table selector, column order, "진행중" state indicator, and 번호/기간 formats. If site structure has changed since spec, adjust field mapping in Step 3.

- [ ] **Step 1: Write failing test `tests/test_source_assembly_bbs.py`**

```python
from pathlib import Path
from unittest.mock import patch
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
        assert it.external_id  # non-empty
        assert it.title
        assert it.org
        assert it.url.startswith("https://assembly.go.kr")


def test_deadline_parsed_from_period(html_bytes):
    src = AssemblyBbsSource()
    items = src._parse(html_bytes)
    # At least one item should have a deadline parsed
    with_deadline = [i for i in items if i.deadline is not None]
    assert with_deadline
    for it in with_deadline:
        assert isinstance(it.deadline, date)


def test_fetch_uses_http_and_paginates_when_full(monkeypatch, html_bytes):
    src = AssemblyBbsSource()
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        class R:
            content = html_bytes
            status_code = 200
            def raise_for_status(self): pass
        return R()

    monkeypatch.setattr("src.sources.assembly_bbs.requests.get", fake_get)
    items = src.fetch()
    # At minimum page 1 fetched
    assert any("pageIndex=1" in u or "list.do" in u for u in calls)
    assert len(items) > 0
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/test_source_assembly_bbs.py -x`
Expected: `ImportError`.

- [ ] **Step 3: Implement `src/sources/assembly_bbs.py`**

The exact CSS/XPath selectors depend on the captured fixture. Use the following template and fill in selectors based on the actual HTML:

```python
from __future__ import annotations
import time
from datetime import date, datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base import JobItem

LIST_URL = "https://assembly.go.kr/portal/bbs/B0000038/list.do"
BASE = "https://assembly.go.kr"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) IG-jobs-bot"


class AssemblyBbsSource:
    name = "assembly_bbs"
    category = "국회"

    def __init__(self, per_page: int = 10, max_pages: int = 2) -> None:
        self.per_page = per_page
        self.max_pages = max_pages

    def fetch(self) -> list[JobItem]:
        all_items: list[JobItem] = []
        for page in range(1, self.max_pages + 1):
            params = {"menuNo": "600097", "sttus": "진행중", "pageIndex": str(page)}
            resp = requests.get(
                LIST_URL, params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            page_items = self._parse(resp.content)
            all_items.extend(page_items)
            # Stop pagination when page is not full (no new items likely earlier)
            if len(page_items) < self.per_page:
                break
            time.sleep(1)  # polite interval
        return all_items

    def _parse(self, html: bytes) -> list[JobItem]:
        soup = BeautifulSoup(html, "lxml")
        now = datetime.now(timezone.utc)
        items: list[JobItem] = []

        # TODO(discovery): Replace with actual selector based on fixture.
        # Example: table.board-list tbody tr
        rows = soup.select("table tbody tr")
        for tr in rows:
            cells = tr.find_all("td")
            if len(cells) < 5:  # skip malformed
                continue

            # Column layout (verify in fixture):
            # [번호] [상태] [제목(link)] [담당부서] [기간] [작성일] [조회]
            # Note: server-side filter (sttus=진행중) is preferred over text matching
            # because the state cell may use icons or badges rather than text.

            external_id = cells[0].get_text(strip=True)
            title_a = cells[2].find("a")
            if not title_a or not external_id.isdigit():
                continue
            # NOTE: state column often contains an icon/badge. get_text() may return "".
            # We rely on the `sttus=진행중` query param for server-side filtering.
            # If the query param proves ineffective in the fixture, either (a) parse the
            # state cell's class name (e.g., `status-active`) or (b) parse the state cell's
            # img alt/title. Iterate until Step 4 tests pass on fresh fixture.
            title = title_a.get_text(strip=True)
            href = title_a.get("href", "")
            url = urljoin(BASE, href)
            org = cells[3].get_text(strip=True)
            period = cells[4].get_text(" ", strip=True)
            deadline = self._parse_deadline(period)

            items.append(JobItem(
                source=self.name, category=self.category,
                external_id=external_id, title=title, org=org,
                deadline=deadline, url=url, fetched_at=now,
            ))
        return items

    @staticmethod
    def _parse_deadline(period: str) -> date | None:
        # Format examples: "2026-07-03 ~ 2026-07-10", "2026.07.03 ~ 2026.07.10"
        import re
        m = re.findall(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})", period)
        if len(m) >= 2:
            y, mo, d = m[-1]
            try:
                return date(int(y), int(mo), int(d))
            except ValueError:
                return None
        return None
```

- [ ] **Step 4: Iterate selectors against fixture until tests pass**

Run: `pytest tests/test_source_assembly_bbs.py -v`
Adjust selectors, column indexes, deadline regex until all three tests pass. If the site markup wildly differs from expectations, capture screenshot of fixture, note the actual structure, adapt.

- [ ] **Step 5: Commit**

```bash
git add src/sources/assembly_bbs.py tests/test_source_assembly_bbs.py tests/fixtures/assembly_bbs_page1.html
git commit -m "feat: parser for 국회 의원실채용 (assembly_bbs)"
```

---

## Task 4: Source — `assembly_dataA` (국회 국회채용)

**Files:**
- Create: `src/sources/assembly_dataA.py`
- Create: `tests/fixtures/assembly_dataA_page1.html`
- Create: `tests/fixtures/assembly_dataA_detail.html`
- Test: `tests/test_source_assembly_dataA.py`

- [ ] **Step 0: Capture fixtures**

```bash
curl -sL 'https://assembly.go.kr/portal/cnts/cntsCont/dataA.do?menuNo=600107&cntsDivCd=JOB' \
  -H 'User-Agent: Mozilla/5.0 IG-jobs-bot' \
  > tests/fixtures/assembly_dataA_page1.html
```

Open in browser, click any active item, capture the detail page HTML too → `assembly_dataA_detail.html`. Note deadline location in detail page.

- [ ] **Step 1: Write failing test**

```python
from pathlib import Path
import pytest
from datetime import date
from src.sources.assembly_dataA import AssemblyDataASource

FIX = Path(__file__).parent / "fixtures"


def test_parses_list_page_with_org_and_title():
    html = (FIX / "assembly_dataA_page1.html").read_bytes()
    src = AssemblyDataASource()
    items = src._parse_list(html)
    assert len(items) > 0
    for it in items:
        assert it.source == "assembly_dataA"
        assert it.category == "국회"
        assert it.org  # 소속기관명 populated
        assert it.title
        assert it.url.startswith("https://assembly.go.kr")


def test_deadline_extracted_from_detail_page():
    html = (FIX / "assembly_dataA_detail.html").read_bytes()
    src = AssemblyDataASource()
    d = src._parse_detail_deadline(html)
    assert isinstance(d, date) or d is None  # may legitimately be None for some
    # For fixture we captured, expect a concrete date — assert non-None if applicable


def test_fetch_only_hits_detail_for_new_items(monkeypatch):
    """Verify that detail-page fetches are opt-in via a hook, not automatic."""
    html_list = (FIX / "assembly_dataA_page1.html").read_bytes()
    src = AssemblyDataASource()
    hits = []
    def fake_get(url, **kw):
        hits.append(url)
        class R:
            content = html_list
            status_code = 200
            def raise_for_status(self): pass
        return R()
    monkeypatch.setattr("src.sources.assembly_dataA.requests.get", fake_get)
    items = src.fetch()
    # Should NOT hit detail pages during list fetch
    assert all("dataA.do" in u for u in hits)
    assert all(it.deadline is None for it in items)  # deadline empty from list
```

- [ ] **Step 2: Run — ImportError expected**

- [ ] **Step 3: Implement `src/sources/assembly_dataA.py`**

```python
from __future__ import annotations
import time
import re
from datetime import date, datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base import JobItem

LIST_URL = "https://assembly.go.kr/portal/cnts/cntsCont/dataA.do"
BASE = "https://assembly.go.kr"
USER_AGENT = "Mozilla/5.0 IG-jobs-bot"


class AssemblyDataASource:
    name = "assembly_dataA"
    category = "국회"

    def __init__(self, per_page: int = 10, max_pages: int = 2) -> None:
        self.per_page = per_page
        self.max_pages = max_pages

    def fetch(self) -> list[JobItem]:
        items: list[JobItem] = []
        for page in range(1, self.max_pages + 1):
            params = {"menuNo": "600107", "cntsDivCd": "JOB", "pageIndex": str(page)}
            resp = requests.get(LIST_URL, params=params,
                                headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
            page_items = self._parse_list(resp.content)
            items.extend(page_items)
            if len(page_items) < self.per_page:
                break
            time.sleep(1)
        return items

    def enrich_with_deadline(self, item: JobItem) -> JobItem:
        """Fetch detail page and merge parsed deadline. Called by main only for new items."""
        try:
            resp = requests.get(item.url, headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
            deadline = self._parse_detail_deadline(resp.content)
            if deadline is None:
                return item
            # frozen dataclass → construct new
            from dataclasses import replace
            return replace(item, deadline=deadline)
        except Exception:
            return item

    def _parse_list(self, html: bytes) -> list[JobItem]:
        soup = BeautifulSoup(html, "lxml")
        now = datetime.now(timezone.utc)
        items: list[JobItem] = []
        # TODO(discovery): confirm row selector
        for tr in soup.select("table tbody tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            external_id = cells[0].get_text(strip=True)
            if not external_id.isdigit():
                continue
            org = cells[1].get_text(strip=True)
            title_a = cells[2].find("a")
            if not title_a:
                continue
            title = title_a.get_text(strip=True)
            href = title_a.get("href", "")
            url = urljoin(BASE, href)
            items.append(JobItem(
                source=self.name, category=self.category,
                external_id=external_id, title=title, org=org,
                deadline=None,  # populated by enrich_with_deadline later
                url=url, fetched_at=now,
            ))
        return items

    @staticmethod
    def _parse_detail_deadline(html: bytes) -> date | None:
        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        # Try common patterns: 마감일 2026-07-10, ~ 2026.07.10, 접수기간 2026-07-01 ~ 2026-07-10
        m = re.search(r"(?:마감|접수|기간)[^0-9]{0,10}(\d{4})[-.](\d{1,2})[-.](\d{1,2})"
                      r"(?:[^0-9]+(\d{4})[-.](\d{1,2})[-.](\d{1,2}))?", text)
        if not m:
            return None
        groups = m.groups()
        # If a range matched, use second date
        if groups[3]:
            y, mo, d = groups[3], groups[4], groups[5]
        else:
            y, mo, d = groups[0], groups[1], groups[2]
        try:
            return date(int(y), int(mo), int(d))
        except ValueError:
            return None
```

- [ ] **Step 4: Iterate selectors → tests green**

- [ ] **Step 5: Commit**

```bash
git add src/sources/assembly_dataA.py tests/test_source_assembly_dataA.py tests/fixtures/assembly_dataA_*.html
git commit -m "feat: parser for 국회 국회채용 (assembly_dataA) with detail deadline"
```

---

## Task 5: Source — `selub_local` (셀럽어스 지방의회, Playwright)

**Files:**
- Create: `src/sources/selub.py`
- Create: `tests/fixtures/selub_rendered.html` (post-JS-render snapshot)
- Test: `tests/test_source_selub.py`

- [ ] **Step 0: Discovery — check robots.txt and capture DOM snapshot**

```bash
curl -sL https://www.selub.us/robots.txt
```

If explicit `Disallow: /recruit`, STOP and surface to human. Reconsider source or ask permission.

Assuming OK, capture rendered DOM:

```bash
python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    page.goto("https://www.selub.us/recruit/all", wait_until="networkidle")
    # Click 지방의회 category tab — selector TBD after inspection
    # page.click('text="지방의회"')
    # Filter 진행중 — selector TBD
    page.wait_for_timeout(2000)
    open("tests/fixtures/selub_rendered.html","w").write(page.content())
    b.close()
PY
```

Also open DevTools Network tab in browser and check if there's a JSON XHR endpoint. If yes, note the URL and payload — Step 3 can pivot to `requests`-only.

- [ ] **Step 1: Failing test `tests/test_source_selub.py`**

```python
from pathlib import Path
import pytest
from src.sources.selub import SelubLocalSource

FIX = Path(__file__).parent / "fixtures" / "selub_rendered.html"


def test_parses_지방의회_items_only():
    html = FIX.read_text(encoding="utf-8")
    src = SelubLocalSource()
    items = src._parse(html)
    assert len(items) > 0
    for it in items:
        assert it.source == "selub_local"
        assert it.category == "지방의회"
        assert it.title
        assert it.url.startswith("https://www.selub.us")
        assert it.external_id


def test_selector_failure_raises():
    """Missing tab/filter/container selectors → RuntimeError so main can skip source."""
    src = SelubLocalSource()
    with pytest.raises(RuntimeError, match="selector"):
        src._parse("<html><body>totally different structure</body></html>")


def test_category_scope_prevents_leakage_from_other_categories():
    """Items outside the 지방의회 container must not be emitted as 지방의회."""
    html = """
    <html><body>
      <div data-category="국회">
        <div class="recruit-item" data-recruit-id="A"><a href="/r/A" class="title">국회아이템</a></div>
      </div>
      <div data-category="지방의회">
        <div class="recruit-item" data-recruit-id="B"><a href="/r/B" class="title">지방의회아이템</a></div>
      </div>
    </body></html>
    """
    src = SelubLocalSource()
    items = src._parse(html)
    assert [i.external_id for i in items] == ["B"]
```

- [ ] **Step 2: Run — ImportError expected**

- [ ] **Step 3: Implement `src/sources/selub.py`**

Two-path structure — try JSON API first (populated after discovery), fall back to Playwright:

```python
from __future__ import annotations
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from src.sources.base import JobItem

BASE = "https://www.selub.us"


class SelubLocalSource:
    name = "selub_local"
    category = "지방의회"

    def fetch(self) -> list[JobItem]:
        # Prefer JSON API if discovered in Task 5 Step 0.
        # Placeholder: use Playwright until API confirmed.
        html = self._fetch_rendered_html()
        return self._parse(html)

    def _fetch_rendered_html(self) -> str:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent="IG-jobs-bot / research")
                page.goto(f"{BASE}/recruit/all", wait_until="networkidle", timeout=30_000)
                # TODO(discovery): fill in selectors
                # page.click('button[data-category="지방의회"]')
                # page.click('button[data-status="active"]')
                page.wait_for_selector(".recruit-item, [data-recruit-id]", timeout=15_000)
                return page.content()
            finally:
                browser.close()

    def _parse(self, html: str) -> list[JobItem]:
        soup = BeautifulSoup(html, "lxml")
        # Scope selector to the 지방의회 category section only. This is a hard
        # correctness requirement — we must NOT emit items from 국회/외부 categories
        # under the "지방의회" label. Selectors TBD from Step 0 discovery.
        # TODO(discovery): replace with actual scope selector.
        scope = (
            soup.select_one('[data-category="지방의회"]')
            or soup.select_one('.category-지방의회')
            or soup.select_one('section:has(.tab-active:-soup-contains("지방의회"))')
        )
        if scope is None:
            raise RuntimeError(
                "selector failed to find 지방의회 category container — page structure changed?"
            )
        containers = scope.select(".recruit-item, [data-recruit-id]")
        if not containers:
            raise RuntimeError("selector produced 0 results within 지방의회 scope — page structure changed?")
        now = datetime.now(timezone.utc)
        items: list[JobItem] = []
        for c in containers:
            title_el = c.select_one(".title, h3, [data-title]")
            org_el = c.select_one(".org, .council, [data-org]")
            link_el = c.select_one("a[href]")
            if not (title_el and link_el):
                continue
            href = link_el["href"]
            url = urljoin(BASE, href)
            # external_id: prefer data-id, else last URL segment
            ext_id = c.get("data-recruit-id") or href.rstrip("/").rsplit("/", 1)[-1]
            deadline = None  # try parsing from a .deadline element in discovery
            items.append(JobItem(
                source=self.name, category=self.category,
                external_id=str(ext_id),
                title=title_el.get_text(strip=True),
                org=org_el.get_text(strip=True) if org_el else "",
                deadline=deadline, url=url, fetched_at=now,
            ))
        return items
```

- [ ] **Step 4: Iterate selectors → tests green**

- [ ] **Step 5: If JSON API found, replace `_fetch_rendered_html` with `requests.get(json_endpoint)` + parse JSON**

- [ ] **Step 6: Commit**

```bash
git add src/sources/selub.py tests/test_source_selub.py tests/fixtures/selub_rendered.html
git commit -m "feat: parser for 셀럽어스 지방의회 (selub_local)"
```

---

## Task 6: Config & Timezone Helpers

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Failing test**

```python
from datetime import datetime, timezone, timedelta
import pytest
from src.config import kst_now, session_label, size_class


def test_kst_now_is_kst_offset():
    now = kst_now()
    assert now.utcoffset() == timedelta(hours=9)


def test_session_label_am_pm():
    kst = timezone(timedelta(hours=9))
    d10 = datetime(2026, 7, 3, 10, 0, tzinfo=kst)
    d18 = datetime(2026, 7, 3, 18, 0, tzinfo=kst)
    assert session_label(d10) == "AM 10시"
    assert session_label(d18) == "PM 6시"


def test_size_class_tiers():
    assert size_class(0) == 1
    assert size_class(10) == 1
    assert size_class(11) == 2
    assert size_class(20) == 2
    assert size_class(21) == 3
    assert size_class(31) == 4
```

- [ ] **Step 2: Run — ImportError expected**

- [ ] **Step 3: Implement `src/config.py`**

```python
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def kst_now() -> datetime:
    return datetime.now(tz=KST)


def session_label(dt: datetime) -> str:
    hour = dt.astimezone(KST).hour
    if hour == 10:
        return "AM 10시"
    if hour == 18:
        return "PM 6시"
    # unusual (manual run) — default to hour label
    return f"{'AM' if hour < 12 else 'PM'} {hour if hour <= 12 else hour - 12}시"


def size_class(total_items: int) -> int:
    if total_items <= 10:
        return 1
    if total_items <= 20:
        return 2
    if total_items <= 30:
        return 3
    return 4


def env(key: str, default: str | None = None, required: bool = False) -> str:
    v = os.environ.get(key, default)
    if required and not v:
        raise RuntimeError(f"missing required env {key}")
    return v or ""
```

- [ ] **Step 4: Run tests → PASS**

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: KST, session label, size class helpers"
```

---

## Task 7: Renderer — HTML template + Playwright screenshot

**Files:**
- Create: `src/templates/digest.html.j2`
- Create: `src/templates/digest.css`
- Create: `src/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: Write template `src/templates/digest.html.j2`**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>{{ css }}</style>
</head>
<body>
<div class="page sz-{{ size_class }}">
  <header>
    <div class="date">{{ date_kst }} · {{ session_label }}</div>
    <h1>오늘의 새 공고
      {% if items_국회 %}· 국회 {{ items_국회|length }}{% endif %}
      {% if items_지방의회 %}· 지방의회 {{ items_지방의회|length }}{% endif %}
    </h1>
  </header>

  {% if items_국회 %}
  <section class="cat">
    <div class="cat-label">국회</div>
    <ul>
      {% for it in items_국회 %}
      <li>· {{ it.org }} · {{ it.title }}{% if it.deadline %} · ~{{ it.deadline.strftime('%-m/%-d') }}{% endif %}</li>
      {% endfor %}
      {% if truncated_국회 %}<li class="more">· 외 {{ truncated_국회 }}건</li>{% endif %}
    </ul>
  </section>
  {% endif %}

  {% if items_지방의회 %}
  <section class="cat">
    <div class="cat-label">지방의회</div>
    <ul>
      {% for it in items_지방의회 %}
      <li>· {{ it.org }} · {{ it.title }}{% if it.deadline %} · ~{{ it.deadline.strftime('%-m/%-d') }}{% endif %}</li>
      {% endfor %}
      {% if truncated_지방의회 %}<li class="more">· 외 {{ truncated_지방의회 }}건</li>{% endif %}
    </ul>
  </section>
  {% endif %}

  <footer class="brand">@{{ ig_handle }}</footer>
</div>
</body>
</html>
```

- [ ] **Step 2: Write CSS `src/templates/digest.css`**

```css
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1080px; height: 1350px; background: #1e3a5f; color: #fff; font-family: 'Pretendard', sans-serif; }
.page { width: 1080px; height: 1350px; padding: 72px 80px; display: flex; flex-direction: column; }
header .date { font-size: 22px; opacity: 0.7; letter-spacing: 2px; margin-bottom: 12px; }
header h1 { font-size: 46px; font-weight: 800; line-height: 1.25; margin-bottom: 48px; }
.cat { margin-bottom: 36px; }
.cat-label { font-size: 22px; letter-spacing: 3px; opacity: 0.7; text-transform: uppercase; border-bottom: 1px solid rgba(255,255,255,0.25); padding-bottom: 8px; margin-bottom: 16px; }
ul { list-style: none; }
li { font-size: 26px; line-height: 1.55; word-break: keep-all; }
li.more { opacity: 0.7; font-size: 22px; margin-top: 6px; }
footer.brand { margin-top: auto; text-align: right; opacity: 0.5; font-size: 20px; }

/* Size tiers */
.sz-2 header h1 { font-size: 40px; margin-bottom: 36px; }
.sz-2 li { font-size: 22px; line-height: 1.5; }
.sz-2 .cat { margin-bottom: 28px; }

.sz-3 header h1 { font-size: 36px; margin-bottom: 28px; }
.sz-3 li { font-size: 19px; line-height: 1.45; }
.sz-3 .cat { margin-bottom: 22px; }

.sz-4 header h1 { font-size: 32px; margin-bottom: 22px; }
.sz-4 li { font-size: 16px; line-height: 1.4; }
.sz-4 .cat { margin-bottom: 18px; }
```

- [ ] **Step 3: Failing test `tests/test_render.py`**

```python
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


def test_html_omits_empty_category_section():
    items = [_item("국회", "1")]
    html = render_digest_html(items, session_label="AM 10시",
                              date_kst="2026-07-03", ig_handle="polty.jobs")
    # cat-label 국회 present, 지방의회 label not
    assert '지방의회</div>' not in html
    assert '국회</div>' in html


def test_html_size_class_scales_with_count():
    items_small = [_item("국회", str(i)) for i in range(5)]
    items_large = [_item("국회", str(i)) for i in range(25)]
    assert "sz-1" in render_digest_html(items_small, "AM 10시", "2026-07-03", "x")
    assert "sz-3" in render_digest_html(items_large, "AM 10시", "2026-07-03", "x")


def test_png_output_dimensions(tmp_path: Path):
    items = [_item("국회", "1")]
    out = tmp_path / "test.png"
    render_digest_png(items, session_label="AM 10시", date_kst="2026-07-03",
                      ig_handle="x", output_path=out)
    assert out.exists()
    from PIL import Image
    with Image.open(out) as im:
        assert im.size == (1080, 1350)


def test_truncation_when_overflow_detected(tmp_path: Path):
    """60+ long items should trigger truncation with '외 N건' marker."""
    items = [_item("국회", str(i),
                   title=f"매우 매우 매우 매우 긴 채용공고 제목입니다 번호 {i}",
                   org=f"○○○의원실{i}")
             for i in range(60)]
    out = tmp_path / "overflow.png"
    result = render_digest_png(items, session_label="AM 10시",
                               date_kst="2026-07-03", ig_handle="x",
                               output_path=out)
    assert out.exists()
    assert result["truncated_국회"] > 0, "expected truncation to kick in for 60-item flood"
```

- [ ] **Step 4: Implement `src/render.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.sources.base import JobItem
from src.config import size_class

TEMPLATES_DIR = Path(__file__).parent / "templates"
CSS_PATH = TEMPLATES_DIR / "digest.css"


def _split_by_category(items: list[JobItem]) -> tuple[list[JobItem], list[JobItem]]:
    guk = [i for i in items if i.category == "국회"]
    jib = [i for i in items if i.category == "지방의회"]
    return guk, jib


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def render_digest_html(
    items: list[JobItem], *,
    session_label: str, date_kst: str, ig_handle: str,
    truncated_국회: int = 0, truncated_지방의회: int = 0,
) -> str:
    guk, jib = _split_by_category(items)
    template = _env().get_template("digest.html.j2")
    css = CSS_PATH.read_text(encoding="utf-8")
    return template.render(
        css=css,
        size_class=size_class(len(items)),
        date_kst=date_kst,
        session_label=session_label,
        items_국회=guk,
        items_지방의회=jib,
        truncated_국회=truncated_국회,
        truncated_지방의회=truncated_지방의회,
        ig_handle=ig_handle,
    )


def render_digest_png(
    items: list[JobItem], *,
    session_label: str, date_kst: str, ig_handle: str,
    output_path: Path,
) -> dict[str, int]:
    """Render items to output_path. Returns {'truncated_국회': N, 'truncated_지방의회': N}."""
    from playwright.sync_api import sync_playwright

    truncated_국회 = truncated_지방의회 = 0
    guk, jib = _split_by_category(items)

    def _screenshot_or_overflow(html: str) -> bool:
        """Return True if content fit and screenshot was taken, else False."""
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1080, "height": 1350})
                page.set_content(html, wait_until="networkidle")
                overflow = page.evaluate("""() => {
                    const b = document.body;
                    return b.scrollHeight > 1350 || b.scrollWidth > 1080;
                }""")
                if not overflow:
                    page.screenshot(path=str(output_path), full_page=False,
                                    clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
                    return True
                return False
            finally:
                browser.close()

    def _trunc(lst: list[JobItem]) -> tuple[list[JobItem], int]:
        if not lst:
            return lst, 0
        drop = max(1, len(lst) // 5)
        return lst[:-drop], drop

    for _ in range(4):
        html = render_digest_html(
            guk + jib, session_label=session_label, date_kst=date_kst,
            ig_handle=ig_handle,
            truncated_국회=truncated_국회, truncated_지방의회=truncated_지방의회,
        )
        if _screenshot_or_overflow(html):
            return {"truncated_국회": truncated_국회, "truncated_지방의회": truncated_지방의회}
        guk, dropped_guk = _trunc(guk)
        jib, dropped_jib = _trunc(jib)
        truncated_국회 += dropped_guk
        truncated_지방의회 += dropped_jib

    # Give up: force screenshot even if overflow (viewport clip preserves 1080x1350)
    html = render_digest_html(
        guk + jib, session_label=session_label, date_kst=date_kst,
        ig_handle=ig_handle,
        truncated_국회=truncated_국회, truncated_지방의회=truncated_지방의회,
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            page.set_content(html, wait_until="networkidle")
            page.screenshot(path=str(output_path), full_page=False,
                            clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
        finally:
            browser.close()
    return {"truncated_국회": truncated_국회, "truncated_지방의회": truncated_지방의회}
```

- [ ] **Step 5: Run tests → PASS (may need a `playwright install chromium` first)**

Run: `pytest tests/test_render.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/templates/ src/render.py tests/test_render.py
git commit -m "feat: HTML digest template + Playwright PNG renderer with overflow truncation"
```

---

## Task 8: Instagram Graph API Client

**Files:**
- Create: `src/instagram.py`
- Test: `tests/test_instagram.py`

- [ ] **Step 1: Failing test using `responses` mock**

```python
import pytest
import responses
from src.instagram import InstagramClient, InstagramError


@responses.activate
def test_publish_flow_calls_container_then_publish():
    responses.add(
        responses.POST,
        "https://graph.facebook.com/v19.0/BIZ_ID/media",
        json={"id": "CREATION_123"}, status=200,
    )
    responses.add(
        responses.GET,
        "https://graph.facebook.com/v19.0/CREATION_123",
        json={"status_code": "FINISHED"}, status=200,
    )
    responses.add(
        responses.POST,
        "https://graph.facebook.com/v19.0/BIZ_ID/media_publish",
        json={"id": "POST_999"}, status=200,
    )

    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN")
    post_id = c.publish_image(image_url="https://x/img.png", caption="hi")
    assert post_id == "POST_999"


@responses.activate
def test_publish_retries_on_5xx_then_succeeds():
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  status=502)
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  json={"id": "C1"}, status=200)
    responses.add(responses.GET,
                  "https://graph.facebook.com/v19.0/C1",
                  json={"status_code": "FINISHED"}, status=200)
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media_publish",
                  json={"id": "P1"}, status=200)
    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN", retry_wait_seconds=0)
    assert c.publish_image("https://x/img.png", "hi") == "P1"


@responses.activate
def test_container_status_polling_times_out_raises():
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  json={"id": "C1"}, status=200)
    # Always in progress
    for _ in range(40):
        responses.add(responses.GET,
                      "https://graph.facebook.com/v19.0/C1",
                      json={"status_code": "IN_PROGRESS"}, status=200)
    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN",
                        poll_interval_seconds=0, poll_timeout_seconds=1)
    with pytest.raises(InstagramError, match="container.*timed out"):
        c.publish_image("https://x/img.png", "hi")
```

- [ ] **Step 2: Run — ImportError expected**

- [ ] **Step 3: Implement `src/instagram.py`**

```python
from __future__ import annotations
import time
import requests


class InstagramError(RuntimeError):
    pass


class InstagramClient:
    API = "https://graph.facebook.com/v19.0"

    def __init__(self, business_id: str, access_token: str, *,
                 poll_interval_seconds: float = 2.0,
                 poll_timeout_seconds: float = 60.0,
                 retry_wait_seconds: float = 5.0) -> None:
        self.business_id = business_id
        self.access_token = access_token
        self.poll_interval = poll_interval_seconds
        self.poll_timeout = poll_timeout_seconds
        self.retry_wait = retry_wait_seconds

    def publish_image(self, image_url: str, caption: str) -> str:
        creation_id = self._create_container(image_url, caption)
        self._wait_container_ready(creation_id)
        return self._publish(creation_id)

    def _create_container(self, image_url: str, caption: str) -> str:
        def call():
            return requests.post(
                f"{self.API}/{self.business_id}/media",
                params={"image_url": image_url, "caption": caption,
                        "access_token": self.access_token},
                timeout=30,
            )
        resp = self._with_retry(call, "create container")
        return resp.json()["id"]

    def _wait_container_ready(self, creation_id: str) -> None:
        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            r = requests.get(
                f"{self.API}/{creation_id}",
                params={"fields": "status_code", "access_token": self.access_token},
                timeout=30,
            )
            r.raise_for_status()
            status = r.json().get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise InstagramError("container status ERROR")
            time.sleep(self.poll_interval)
        raise InstagramError("container status polling timed out")

    def _publish(self, creation_id: str) -> str:
        def call():
            return requests.post(
                f"{self.API}/{self.business_id}/media_publish",
                params={"creation_id": creation_id, "access_token": self.access_token},
                timeout=30,
            )
        resp = self._with_retry(call, "publish")
        return resp.json()["id"]

    def _with_retry(self, call, label: str):
        for attempt in (1, 2):
            r = call()
            if r.status_code < 500:
                if r.status_code >= 400:
                    raise InstagramError(f"{label} failed {r.status_code}: {r.text}")
                return r
            if attempt == 1:
                time.sleep(self.retry_wait)
        raise InstagramError(f"{label} failed after retry: {r.status_code}")
```

- [ ] **Step 4: Run tests → PASS**

- [ ] **Step 5: Commit**

```bash
git add src/instagram.py tests/test_instagram.py
git commit -m "feat: Instagram Graph API client with retry + status polling"
```

---

## Task 9: Main Orchestrator (two-phase: `render` + `publish`)

**Design rationale:** The workflow needs to (a) render a PNG, (b) commit+push it so its raw URL is reachable, (c) then call Instagram Graph API pointing at that raw URL, (d) then commit updated state. Two separate Python invocations solve this cleanly: `render` writes `pending.json` describing what should be posted; `publish` reads `pending.json`, uploads to IG, updates `state.json`, and deletes `pending.json`. This avoids re-fetching sources twice, avoids filename-race bugs at minute boundaries, and gives each command a single unambiguous responsibility.

**Files:**
- Create: `src/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Failing tests `tests/test_main.py`**

```python
import json
from datetime import date, datetime, timezone
from pathlib import Path
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
    # state.json absent → treated as empty → bootstrap
    with patch("src.main._instantiate_sources") as srcs, \
         patch("src.main.render_digest_png") as rend:
        s = MagicMock(); s.name = "assembly_bbs"
        s.fetch.return_value = [_item("assembly_bbs", "9560"), _item("assembly_bbs", "9561")]
        srcs.return_value = [s]
        rc = cmd_render(state_path=state_p, posts_dir=posts, pending_path=pending_p,
                        session_label="AM 10시", date_kst="2026-07-03", ig_handle="x")
        assert rc == 0
        rend.assert_not_called()
        # state saved with items recorded
        state = json.loads(state_p.read_text())
        assert set(state["seen"]["assembly_bbs"]) == {"9560", "9561"}
        # pending is empty
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
        assert not pending_p.exists()  # cleaned up


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
        args, kwargs = client.publish_image.call_args
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
        assert pending_p.exists()  # NOT deleted on failure — allows retry
```

- [ ] **Step 2: Run — ImportError expected**

Run: `pytest tests/test_main.py -x`

- [ ] **Step 3: Implement `src/main.py`**

```python
from __future__ import annotations
import argparse
import concurrent.futures
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from src.config import KST, kst_now, session_label as make_session_label, env
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


def cmd_render(*, state_path: Path, posts_dir: Path, pending_path: Path,
               session_label: str, date_kst: str, ig_handle: str) -> int:
    """Fetch + dedupe + render PNG. Write pending.json. Do NOT touch state (except bootstrap) or IG."""
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
        # Bootstrap: filter_new already recorded items into state via mutation.
        state.last_run_at = kst_now()
        state.save(state_path)
        log.info("bootstrap complete, %d items marked as seen",
                 sum(len(v) for v in state.seen.values()))
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
        new, session_label=session_label, date_kst=date_kst,
        ig_handle=ig_handle, output_path=png_path)
    log.info("rendered %s (%d items; truncated 국회=%d 지방의회=%d)",
             png_path, len(new),
             result.get("truncated_국회", 0), result.get("truncated_지방의회", 0))

    pending_path.write_text(json.dumps({
        "new": [_item_to_dict(i) for i in new],
        "png": png_path.name,
        "session_label": session_label,
        "counts": _summary_counts(new),
    }, ensure_ascii=False), encoding="utf-8")
    return 0


def cmd_publish(*, pending_path: Path, state_path: Path,
                ig_business_id: str, ig_access_token: str,
                raw_url_base: str) -> int:
    """Read pending.json → upload to IG → update state.json → delete pending.json.
    On IG failure: exit 1, keep pending.json (workflow can retry)."""
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
```

- [ ] **Step 4: Run tests → PASS**

Run: `pytest tests/test_main.py -v`
Expected: 8 passed.

- [ ] **Step 5: Local smoke test**

```bash
python -m src.main render --state state.json --posts-dir posts --pending pending.json
cat pending.json
# First-ever run: bootstrap. state.json created, pending.json shows {"new":[],"png":null}
# Second run (nothing new): pending.json again {"new":[],"png":null}
```

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: main orchestrator with explicit render/publish phases"
```

---

## Task 10: CI Workflow — `test.yml`

**Files:**
- Create: `.github/workflows/test.yml`

- [ ] **Step 1: Write `test.yml`**

```yaml
name: test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install
        run: |
          pip install -e '.[dev]'
          python -m playwright install --with-deps chromium
      - name: Ruff
        run: ruff check src tests
      - name: Pytest
        run: pytest -v
```

- [ ] **Step 2: Verify workflow syntax locally (optional, via `act` or GitHub push)**

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add pytest+ruff workflow"
```

---

## Task 11: CI Workflow — `post.yml` (cron)

**Files:**
- Create: `.github/workflows/post.yml`

- [ ] **Step 1: Write `post.yml`**

```yaml
name: post

on:
  schedule:
    - cron: "0 1 * * *"   # KST 10:00
    - cron: "0 9 * * *"   # KST 18:00
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Skip Instagram upload / state commit"
        type: boolean
        default: false

permissions:
  contents: write

jobs:
  publish:
    runs-on: ubuntu-latest
    concurrency:
      group: post
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: true
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install deps
        run: |
          pip install -r requirements.txt
          python -m playwright install --with-deps chromium

      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

      # Phase 1: fetch, dedupe, render. Produces pending.json with PNG filename.
      - name: Render
        env:
          IG_HANDLE: ${{ vars.IG_HANDLE || 'polty.jobs' }}
        run: |
          python -m src.main render \
            --state state.json --posts-dir posts --pending pending.json

      # Extract PNG filename + non-empty flag from pending.json using jq.
      - name: Inspect pending
        id: pending
        run: |
          if [ ! -s pending.json ]; then
            echo "has_pending=false" >> $GITHUB_OUTPUT
            exit 0
          fi
          NEW_COUNT=$(jq '.new | length' pending.json)
          PNG=$(jq -r '.png // empty' pending.json)
          if [ "$NEW_COUNT" = "0" ] || [ -z "$PNG" ]; then
            echo "has_pending=false" >> $GITHUB_OUTPUT
          else
            echo "has_pending=true"  >> $GITHUB_OUTPUT
            echo "png=$PNG"          >> $GITHUB_OUTPUT
          fi

      # Bootstrap run may have updated state.json (no PNG). Commit state alone in that case.
      - name: Commit bootstrap state
        if: steps.pending.outputs.has_pending == 'false'
        run: |
          if ! git diff --quiet state.json 2>/dev/null; then
            git add state.json
            git commit -m "state: bootstrap ($(date -u +%FT%TZ))"
            for i in 1 2 3; do
              if git push; then exit 0; fi
              git pull --rebase
            done
            exit 1
          fi

      # Commit + push the specific PNG produced this run (filename from pending.json).
      - name: Commit image
        if: steps.pending.outputs.has_pending == 'true'
        run: |
          git add "posts/${{ steps.pending.outputs.png }}"
          git commit -m "post: image ${{ steps.pending.outputs.png }}"
          for i in 1 2 3; do
            if git push; then exit 0; fi
            git pull --rebase
          done
          exit 1

      # Phase 2: publish to Instagram + update state.
      - name: Publish to Instagram
        if: steps.pending.outputs.has_pending == 'true' && github.event.inputs.dry_run != 'true'
        env:
          IG_ACCESS_TOKEN: ${{ secrets.IG_ACCESS_TOKEN }}
          IG_BUSINESS_ACCOUNT_ID: ${{ secrets.IG_BUSINESS_ACCOUNT_ID }}
        run: |
          RAW_BASE="https://raw.githubusercontent.com/${{ github.repository }}/main/posts"
          python -m src.main publish \
            --pending pending.json --state state.json \
            --raw-url-base "$RAW_BASE"

      - name: Commit state
        if: steps.pending.outputs.has_pending == 'true' && github.event.inputs.dry_run != 'true'
        run: |
          if ! git diff --quiet state.json; then
            git add state.json
            git commit -m "state: mark items seen ($(date -u +%FT%TZ))"
            for i in 1 2 3; do
              if git push; then exit 0; fi
              git pull --rebase
            done
            exit 1
          fi
```

**How this differs from a naive two-pass design:** The PNG filename generated in `render` is written to `pending.json`; the workflow reads it via `jq` and commits exactly that file. No `git status` parsing, no filename-race at minute boundaries, and no re-fetch of sources in `publish`.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/post.yml
git commit -m "ci: add scheduled post workflow (KST 10:00 / 18:00)"
```

---

## Task 12: README + Setup Guide

**Files:**
- Create: `README.md`
- Create: `docs/setup-instagram-graph-api.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# polty-jobs

3개 공공/정치 채용 사이트에서 새 공고를 수집해서 매일 KST 10시·18시에 인스타그램에 다이제스트 형태로 자동 업로드하는 봇.

## 소스
- 국회 의원실채용 (assembly.go.kr B0000038)
- 국회 국회채용 (assembly.go.kr dataA)
- 셀럽어스 지방의회 (selub.us/recruit/all → 지방의회 카테고리)

## 아키텍처
GitHub Actions cron → Python 오케스트레이터 → 3 소스 병렬 fetch → dedup → HTML/Playwright PNG 렌더 → Instagram Graph API 게시 → state.json 커밋.

## 로컬 개발
```
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m playwright install chromium
cp .env.example .env  # 값 채우기
pytest
python -m src.main --dry-run
```

## 배포 (GitHub Actions)
1. GitHub repo 생성 후 push
2. Settings → Secrets → 다음 secrets 등록:
   - `IG_ACCESS_TOKEN` (long-lived)
   - `IG_BUSINESS_ACCOUNT_ID`
3. Actions 탭에서 `post` 워크플로 활성화
4. 초기 1회 실행 시 bootstrap (기존 공고를 seen 처리, 실제 포스트 안 함). 다음 실행부터 새 공고만 포스트.

## 참고
- Instagram Graph API 세팅: `docs/setup-instagram-graph-api.md`
- Design spec: `docs/superpowers/specs/2026-07-03-instagram-jobs-automation-design.md`
```

- [ ] **Step 2: Write `docs/setup-instagram-graph-api.md`**

```markdown
# Instagram Graph API 세팅 가이드

## 1. 계정 준비
- 인스타 앱: Settings → Account Type → **Business** 또는 **Creator**로 전환
- 페이스북 페이지 하나 만들어서 인스타 계정에 연결

## 2. Meta for Developers 앱 생성
1. https://developers.facebook.com/apps/ → Create App
2. Type: **Business**
3. App name/Contact email 입력

## 3. Instagram Graph API 추가
1. 앱 대시보드 → Add Product → **Instagram Graph API** Set up

## 4. 권한 신청 (App Review)
필요한 권한:
- `instagram_basic`
- `instagram_content_publish`
- `pages_show_list`
- `pages_read_engagement`

App Review 필요 (수일~1주 소요). 개발용 토큰은 심사 없이도 발급 가능하지만, 프로덕션 자동 게시는 심사 승인이 있어야 안정적.

## 5. Access Token 발급
1. Graph API Explorer (https://developers.facebook.com/tools/explorer/) 접속
2. 앱 선택, User Token 발급 (권한 위 4개 체크)
3. Access Token Debugger (https://developers.facebook.com/tools/debug/accesstoken/)에서 **Extend Access Token** → 60일 long-lived 토큰
4. Page Access Token으로 교환 → 이것이 실제 API 호출에 쓰는 토큰

**저장:** GitHub Secrets `IG_ACCESS_TOKEN`

## 6. Instagram Business Account ID 조회
```
curl "https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_TOKEN"
# → 페이지 ID 확인, 그 다음:
curl "https://graph.facebook.com/v19.0/{PAGE_ID}?fields=instagram_business_account&access_token=YOUR_TOKEN"
# → instagram_business_account.id 가 IG_BUSINESS_ACCOUNT_ID
```
**저장:** GitHub Secrets `IG_BUSINESS_ACCOUNT_ID`

## 7. 60일 토큰 갱신
- 60일마다 재발급 필요. 만료 임박 시 이메일 알림 오도록 캘린더에 표시.
- 향후 자동화: refresh endpoint로 갱신하는 workflow 추가 검토.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/setup-instagram-graph-api.md
git commit -m "docs: README + Instagram Graph API setup guide"
```

---

## Task 13: End-to-End Local Smoke Test

- [ ] **Step 1: Manual smoke sequence**

```bash
# fresh clone / clean checkout
rm -rf state.json posts/*.png
python -m src.main --dry-run
# expect: bootstrap message, no PNG rendered (first run)

# simulate second run by making state look non-empty
# then invoke dry-run again
python -m src.main --dry-run
# expect: PNG rendered in posts/, "dry-run: skipping IG upload"
```

- [ ] **Step 2: Inspect rendered PNG visually — open `posts/*.png` and confirm layout**

- [ ] **Step 3: Verify tests still pass after full integration**

Run: `pytest -v`
Expected: all green.

- [ ] **Step 4 (no commit — this is verification only)**

---

## Task 14: Prerequisites Checklist (User Actions, outside code)

- [ ] Confirm `robots.txt` for `selub.us` allows the target path
- [ ] Complete Meta App Review for `instagram_content_publish`
- [ ] Extract `IG_ACCESS_TOKEN` (long-lived) and `IG_BUSINESS_ACCOUNT_ID`
- [ ] Create GitHub repo, push code
- [ ] Add secrets `IG_ACCESS_TOKEN`, `IG_BUSINESS_ACCOUNT_ID`
- [ ] (Optional) Add repo variable `IG_HANDLE` matching actual account
- [ ] Trigger workflow manually (`workflow_dispatch`) once with `dry_run=true` to verify plumbing
- [ ] Verify first real cron trigger (bootstrap silent run) works
- [ ] Confirm second cron trigger posts to Instagram

---

## Success Criteria

- Automated post at KST 10:00 & 18:00 with 2 sections (국회 + 지방의회)
- Zero-item runs post nothing
- No duplicate postings across runs (dedup verified)
- Sources fail in isolation without aborting the pipeline
- Test suite green in CI
- Total runtime under 3 minutes per execution
