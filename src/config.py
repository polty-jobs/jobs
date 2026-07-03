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
    if hour < 12:
        return f"AM {hour or 12}시"
    display = hour if hour == 12 else hour - 12
    return f"PM {display}시"


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
