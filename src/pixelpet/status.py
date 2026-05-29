from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    PERMISSION_REQUIRED = "permission_required"
    NEEDS_INPUT = "needs_input"
    FAILED_OFFLINE = "failed_offline"
    WORKING = "working"
    DONE = "done"
    IDLE = "idle"


REQUIRED_STATUSES: tuple[Status, ...] = (
    Status.IDLE,
    Status.WORKING,
    Status.NEEDS_INPUT,
    Status.PERMISSION_REQUIRED,
    Status.DONE,
    Status.FAILED_OFFLINE,
)


STATUS_PRIORITY: dict[Status, int] = {
    Status.PERMISSION_REQUIRED: 60,
    Status.NEEDS_INPUT: 55,
    Status.FAILED_OFFLINE: 50,
    Status.WORKING: 40,
    Status.DONE: 30,
    Status.IDLE: 0,
}


def status_priority(status: Status) -> int:
    return STATUS_PRIORITY[status]

