"""Estado compartilhado pelos grafos."""
from __future__ import annotations

from typing import TypedDict


class S(TypedDict, total=False):
    problem: dict
    result: dict
    prompt: str
    code: str
    raw: str
    attempt: int
    log: list[dict]
