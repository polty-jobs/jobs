from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime
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
        last = raw.get("last_run_at")
        return cls(
            last_run_at=datetime.fromisoformat(last) if last else None,
            seen={k: list(v) for k, v in raw.get("seen", {}).items()},
        )

    def save(self, path: Path) -> None:
        payload = {
            "version": 1,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "seen": self.seen,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(self, items: list[JobItem]) -> None:
        by_source: dict[str, list[str]] = {}
        for it in items:
            by_source.setdefault(it.source, []).append(it.external_id)
        for source, ids in by_source.items():
            existing = self.seen.setdefault(source, [])
            for new_id in ids:
                if new_id not in existing:
                    existing.append(new_id)
            if len(existing) > MAX_SEEN_PER_SOURCE:
                del existing[: len(existing) - MAX_SEEN_PER_SOURCE]


def filter_new(
    items: list[JobItem],
    state: State,
    bootstrap_if_empty: bool = False,
) -> list[JobItem]:
    if bootstrap_if_empty and state.is_empty():
        state.record(items)
        return []
    new: list[JobItem] = []
    for it in items:
        if it.external_id not in state.seen.get(it.source, []):
            new.append(it)
    return new
