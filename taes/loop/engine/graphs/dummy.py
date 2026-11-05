"""Grafo exemplo mínimo para demonstrar como adicionar um novo fluxo."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ...integrations.judge import Submitter
from .state import S


def dummy_prompt(problem_id: str) -> str:
    return (
        "You are in a dummy graph demo.\n"
        "Return a tiny Python script that prints the problem id.\n"
        f"Problem id: {problem_id}\n"
    )


def build_dummy_graph(llm, submit_fn: Submitter):
    def dummy_step(s: S) -> S:
        problem_id = str(s.get("problem", {}).get("id", "unknown"))
        result = {
            "verdict": "DUMMY",
            "time_ms": 0,
            "memory_kb": 0,
            "feedback": "Dummy graph selected. Edit config.py to choose another graph.",
        }
        code = "# Grafo dummy: exemplo de adição de um novo fluxo\nprint(f'problem={problem_id!r}')\n"
        entry = {
            "attempt": 1,
            "prompt": dummy_prompt(problem_id),
            "raw_response": "dummy graph",
            "code": code,
            "result": result,
        }
        return {
            "code": code,
            "result": result,
            "prompt": dummy_prompt(problem_id),
            "attempt": s.get("attempt", 0) + 1,
            "log": s.get("log", []) + [entry],
        }

    g = StateGraph(S)
    g.add_node("dummy_step", dummy_step)
    g.add_edge(START, "dummy_step")
    g.add_edge("dummy_step", END)
    return g.compile()
