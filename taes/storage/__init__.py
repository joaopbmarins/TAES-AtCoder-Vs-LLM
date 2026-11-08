"""Persistência de dados e artefatos da pipeline."""

from .csv import (
    compact_text,
    load_previous,
    read_ids,
    save_attempt,
    save_solution,
    write_error_rows,
    write_results,
)

__all__ = [
    "compact_text",
    "load_previous",
    "read_ids",
    "save_attempt",
    "save_solution",
    "write_error_rows",
    "write_results",
]
