"""Estado compartilhado pelos grafos."""
from __future__ import annotations

from typing import TypedDict

from taes.core.models import JudgeResult, Problem, Sample


class S(TypedDict, total=False):
    problem: Problem
    result: JudgeResult
    prompt: str
    code: str
    raw: str
    attempt: int
    log: list[dict]
    plan: str
    tests: list[Sample]
    submissions: int
    pending_warning: str
