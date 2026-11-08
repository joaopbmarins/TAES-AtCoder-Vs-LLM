"""Dispatcher dos grafos disponíveis do projeto."""
from __future__ import annotations

from ...core.config import AVAILABLE_GRAPHS, GRAPH_NAME
from ..integrations.judge import Submitter
from .graphs.default import build_default_graph
from .graphs.dummy import build_dummy_graph
from .graphs.state import S


def build_graph(llm, submit_fn: Submitter, graph_name: str | None = None):
    """Seleciona um grafo a partir da config.py, permitindo trocar facilmente o fluxo."""
    name = (graph_name or GRAPH_NAME).lower()
    builders = {
        "default": build_default_graph,
        "dummy": build_dummy_graph,
    }
    if name not in builders:
        options = ", ".join(sorted(builders))
        raise ValueError(f"graph '{name}' inválido. Opções válidas: {options}. Use --graph ou GRAPH_NAME em config.py.")
    return builders[name](llm, submit_fn)


__all__ = [
    "S",
    "build_default_graph",
    "build_dummy_graph",
    "build_graph",
    "GRAPH_NAME",
    "AVAILABLE_GRAPHS",
]
