"""Grafo padrão do projeto: build_prompt -> generate -> evaluate -> (reparo | fim)."""
from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..config import FENCE, MAX_ATTEMPTS, MAX_FEEDBACK_CHARS
from ..judge import Submitter
from ..llm import invoke_with_retry


def initial_prompt(statement: str) -> str:
    return (
        "Solve the competitive programming problem in Python 3. Generate only one code block. "
        "The program must read from standard input and write to standard output.\n"
        f'The coding problem:\n\n"""\n{statement}\n"""\n\n'
        f"Use this code block format for your solution:\n\n{FENCE}python\n\n{FENCE}\n"
    )


def repair_prompt(statement: str, error: str, code: str) -> str:
    return (
        "The following Python 3 code that solves the competitive programming problem has an error. "
        "Fix the code and generate only one code block. The program must read from standard input "
        "and write to standard output.\n"
        f'The coding problem:\n\n"""\n{statement}\n"""\n\n'
        f'Error Message:\n\n"""\n{error[:MAX_FEEDBACK_CHARS]}\n"""\n\n'
        f"The code with the error:\n\n{FENCE}python\n{code}\n{FENCE}\n"
    )


_CODE_RE = re.compile(r"```[ \t]*(?:python3?|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(text: str) -> str:
    """Último bloco de código da resposta ('' se não houver)."""
    blocks = _CODE_RE.findall(text or "")
    return blocks[-1].strip() + "\n" if blocks else ""


class S(TypedDict, total=False):
    problem: dict
    result: dict
    prompt: str
    code: str
    raw: str
    attempt: int
    log: list[dict]


def build_default_graph(llm, submit_fn: Submitter):
    def build_prompt(s: S) -> S:
        st = s["problem"]["statement"]
        if not s.get("result"):
            return {"prompt": initial_prompt(st)}
        return {"prompt": repair_prompt(st, s["result"]["feedback"], s["code"])}

    def generate(s: S) -> S:
        text = invoke_with_retry(llm, s["prompt"])
        return {"code": extract_code(text), "raw": text, "attempt": s.get("attempt", 0) + 1}

    def evaluate(s: S) -> S:
        if not s["code"]:
            res = {"verdict": "RE", "time_ms": None, "memory_kb": None, "feedback": "No code block found."}
        else:
            res = submit_fn(s["problem"], s["code"])
        entry = {
            "attempt": s["attempt"],
            "prompt": s["prompt"],
            "raw_response": s["raw"],
            "code": s["code"],
            "result": res,
        }
        return {"result": res, "log": s.get("log", []) + [entry]}

    def route(s: S) -> str:
        done = s["result"]["verdict"] == "AC" or s["attempt"] >= MAX_ATTEMPTS
        return "end" if done else "build_prompt"

    g = StateGraph(S)
    g.add_node("build_prompt", build_prompt)
    g.add_node("generate", generate)
    g.add_node("evaluate", evaluate)
    g.add_edge(START, "build_prompt")
    g.add_edge("build_prompt", "generate")
    g.add_edge("generate", "evaluate")
    g.add_conditional_edges("evaluate", route, {"end": END, "build_prompt": "build_prompt"})
    return g.compile()
