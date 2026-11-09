"""Laço principal: para cada problema do CSV, scraping + grafo + gravação dos resultados."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from taes.storage.csv import (
    compact_text,
    load_previous,
    read_ids,
    save_attempt,
    save_solution,
    write_error_rows,
    write_results,
)

from ...core.config import RECURSION_LIMIT
from ...core.paths import DEFAULT_LOOP_SOLUTIONS_DIR
from ..integrations.llm import get_usage, reset_usage
from ..integrations.scraper import scrape_problem
from .graph import S, build_graph

log = logging.getLogger(__name__)


def run(csv_path: str, out_csv: str, llm, scrape=scrape_problem, submit_fn=None,
        out_dir: str = str(DEFAULT_LOOP_SOLUTIONS_DIR), resume: bool = True,
        delay: float = 1.5, graph_name: str | None = None, err_csv: str | None = None) -> list[dict]:
    if submit_fn is None:
        raise ValueError("submit_fn é obrigatório para execução real do loop.")

    graph = build_graph(llm, submit_fn, graph_name=graph_name)
    ids = read_ids(csv_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    err_path = Path(err_csv) if err_csv else Path(out_csv).with_name(f"{Path(out_csv).stem}_erros.csv")
    err_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_previous(out_csv) if resume else {}
    for n, pid in enumerate(ids, 1):
        if rows.get(pid, {}).get("verdict") == "AC":
            log.info("[%d/%d] %s já resolvido, pulando", n, len(ids), pid)
            continue

        saved = 0
        reset_usage()
        try:
            log.info("[%d/%d] %s: iniciando scraping do problema", n, len(ids), pid)
            problem = scrape(pid)
            log.info("[%d/%d] %s: scraping concluído; samples=%d; title=%s", n, len(ids), pid,
                     len(problem.get("samples", [])), problem.get("title") or "(sem título)")
            if not problem["samples"]:
                raise ValueError("sem exemplos no enunciado")

            log.info("[%d/%d] %s: iniciando grafo do modelo", n, len(ids), pid)
            final: S = {}
            for step_idx, state in enumerate(graph.stream({"problem": problem}, config={"recursion_limit": RECURSION_LIMIT}, stream_mode="values"), 1):
                final = state
                log.info("[%d/%d] %s: passo do grafo #%d; log_entries=%d; attempt=%s", n, len(ids), pid, step_idx,
                         len(state.get("log", [])), state.get("attempt"))
                for entry in state.get("log", [])[saved:]:
                    save_attempt(out / "tentativas" / pid, entry)
                    saved += 1

            res = final["result"]
            row = {
                "problem_id": pid,
                "verdict": res["verdict"],
                "attempts": final["attempt"],
                "time_ms": res.get("time_ms"),
                "memory_kb": res.get("memory_kb"),
                "reason": compact_text(res.get("reason") or res.get("feedback") or res["verdict"]),
                "feedback": compact_text(res.get("feedback")),
                **get_usage(),
            }
            if res["verdict"] == "AC":
                save_solution(out, pid, final["code"])

            log.info("[%d/%d] %s -> %s (tentativas: %s)", n, len(ids), pid, res["verdict"],
                     " > ".join(e["result"]["verdict"] for e in final["log"]))
        except Exception as e:
            log.exception("[%d/%d] %s falhou no scraping/grafo/LLM/submissão: %s", n, len(ids), pid, e)
            row = {
                "problem_id": pid,
                "verdict": f"ERROR: {e}",
                "attempts": saved,
                "time_ms": None,
                "memory_kb": None,
                "reason": compact_text(str(e)),
                "feedback": compact_text(str(e)),
                **get_usage(),
            }

        rows[pid] = row
        write_results(out_csv, rows)
        write_error_rows(str(err_path), rows)
        time.sleep(delay)
    return list(rows.values())
