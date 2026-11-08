"""Modelos de dados compartilhados pela pipeline."""
from __future__ import annotations

from typing import TypeAlias, TypedDict

Sample: TypeAlias = tuple[str, str]


class Problem(TypedDict):
    id: str
    contest: str
    title: str
    statement: str
    samples: list[Sample]


class JudgeResult(TypedDict, total=False):
    verdict: str
    time_ms: int | None
    memory_kb: int | None
    reason: str
    feedback: str
    source: str
