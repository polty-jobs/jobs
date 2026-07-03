from __future__ import annotations
from dataclasses import dataclass
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
            raise ValueError(
                f"category must be one of {VALID_CATEGORIES}, got {self.category!r}"
            )

    def dedup_key(self) -> str:
        return f"{self.source}:{self.external_id}"


class Source(Protocol):
    name: str
    category: str

    def fetch(self) -> list[JobItem]:
        ...
