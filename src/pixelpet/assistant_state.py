from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .status import Status


@dataclass(frozen=True)
class SessionUsage:
    value: int
    display_kind: str = "tokens"


@dataclass(frozen=True)
class StatusSnapshot:
    status: Status
    reason: str
    thread_id: str | None = None
    title: str | None = None
    updated_at_ms: int | None = None
    activity: str | None = None
    cost: float | None = None
    usage: SessionUsage | None = None
    source: str = ""
    backend: str | None = None


class StatusReader(Protocol):
    def current_status(self) -> StatusSnapshot:
        ...
