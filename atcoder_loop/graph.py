"""Dispatcher dos grafos disponíveis do projeto."""
from __future__ import annotations

from typing import TypedDict

from .config import AVAILABLE_GRAPHS, GRAPH_NAME
from .graphs.default import build_default_graph
from .graphs.dummy import build_dummy_graph
from .judge import Submitter


class S(TypedDict, total=False):
    problem: dict
    result: dict
    prompt: str
    code: str
    raw: str
    attempt: int
    log: list[dict]


def build_graph(llm, submit_fn: Submitter, graph_name: str | None = None):
    """Seleciona um grafo a partir da config.py, permitindo trocar facilmente o fluxo."""
    name = (graph_name or GRAPH_NAME).lower()
    builders = {
        "default": build_default_graph,
        "dummy": build_dummy_graph,
    }
    allowed = {k: builders[k] for k in AVAILABLE_GRAPHS if k in builders}
    if name not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValueError(f"graph '{name}' inválido. Opções válidas: {options}. Ajuste GRAPH_NAME em config.py.")
    return allowed[name](llm, submit_fn)


__all__ = [
    "S",
    "build_default_graph",
    "build_dummy_graph",
    "build_graph",
    "GRAPH_NAME",
    "AVAILABLE_GRAPHS",
]
