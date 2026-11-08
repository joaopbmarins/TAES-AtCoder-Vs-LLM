"""Integrações externas usadas pelo loop."""

from .judge import submit_atcoder
from .llm import build_llm
from .scraper import scrape_problem

__all__ = ["build_llm", "scrape_problem", "submit_atcoder"]
