"""Builders dos grafos disponíveis do projeto."""

from .default import build_default_graph
from .dummy import build_dummy_graph

__all__ = ["build_default_graph", "build_dummy_graph"]
