from __future__ import annotations
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import size_class
from src.sources.base import JobItem

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
    items: list[JobItem],
    *,
    session_label: str,
    date_kst: str,
    ig_handle: str,
    truncated_국회: int = 0,
    truncated_지방의회: int = 0,
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
    items: list[JobItem],
    *,
    session_label: str,
    date_kst: str,
    ig_handle: str,
    output_path: Path,
) -> dict[str, int]:
    """Render items to PNG at output_path. Returns per-category truncation counts."""
    from playwright.sync_api import sync_playwright

    truncated_국회 = truncated_지방의회 = 0
    guk, jib = _split_by_category(items)

    def _render_and_screenshot(html: str) -> bool:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1080, "height": 1350})
                page.set_content(html, wait_until="networkidle")
                overflow = page.evaluate(
                    "() => document.body.scrollHeight > 1350 || document.body.scrollWidth > 1080"
                )
                if not overflow:
                    page.screenshot(
                        path=str(output_path), full_page=False,
                        clip={"x": 0, "y": 0, "width": 1080, "height": 1350},
                    )
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
            guk + jib,
            session_label=session_label, date_kst=date_kst, ig_handle=ig_handle,
            truncated_국회=truncated_국회, truncated_지방의회=truncated_지방의회,
        )
        if _render_and_screenshot(html):
            return {"truncated_국회": truncated_국회, "truncated_지방의회": truncated_지방의회}
        guk, dropped_guk = _trunc(guk)
        jib, dropped_jib = _trunc(jib)
        truncated_국회 += dropped_guk
        truncated_지방의회 += dropped_jib

    # Give up: screenshot with clip so output is still 1080x1350
    html = render_digest_html(
        guk + jib,
        session_label=session_label, date_kst=date_kst, ig_handle=ig_handle,
        truncated_국회=truncated_국회, truncated_지방의회=truncated_지방의회,
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            page.set_content(html, wait_until="networkidle")
            page.screenshot(
                path=str(output_path), full_page=False,
                clip={"x": 0, "y": 0, "width": 1080, "height": 1350},
            )
        finally:
            browser.close()
    return {"truncated_국회": truncated_국회, "truncated_지방의회": truncated_지방의회}
