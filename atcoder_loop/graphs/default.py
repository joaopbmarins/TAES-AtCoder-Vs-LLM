"""Grafo padrão do projeto: build_prompt -> generate -> evaluate -> (reparo | fim)."""
from __future__ import annotations

import logging
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..config import FENCE, MAX_ATTEMPTS, MAX_FEEDBACK_CHARS
from ..judge import Submitter
from ..llm import invoke_with_retry

log = logging.getLogger(__name__)


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


_CODE_RE = re.compile(
    r"```(?:[ \t]*(?:python3?|py)?[ \t]*)?\r?\n(.*?)\r?\n```",
    re.DOTALL | re.IGNORECASE,
)


def _looks_like_code(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    markers = (
        "def ", "class ", "import ", "from ", "print(", "input(", "return ",
        "#include", "int main", "using namespace", "std::", "cout", "cin",
    )
    lower = text.lower()
    return any(marker.lower() in lower for marker in markers)


def extract_code(text: str) -> str:
    """Último bloco de código da resposta ou, em último caso, um texto que pareça código."""
    blocks = _CODE_RE.findall(text or "")
    if blocks:
        last = blocks[-1].strip()
        if last:
            return last + "\n"

    raw = (text or "").strip()
    if not raw:
        return ""

    stripped = re.sub(r"^```(?:[\w+-]+)?\s*\r?\n|\r?\n```\s*$", "", raw, flags=re.IGNORECASE)
    if stripped.strip() and _looks_like_code(stripped):
        return stripped.strip() + "\n"

    if _looks_like_code(raw):
        return raw + "\n"

    return ""


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
        attempt_no = s.get("attempt", 0) + 1
        log.info("[graph] gerando tentativa %d com modelo=%s", attempt_no,
                 getattr(llm, "model_name", None) or getattr(llm, "model", None) or type(llm).__name__)
        text = invoke_with_retry(llm, s["prompt"])
        code = extract_code(text)
        log.info("[graph] tentativa %d concluída; codigo_len=%d; raw_len=%d", attempt_no, len(code), len(text))
        return {"code": code, "raw": text, "attempt": attempt_no}

    def evaluate(s: S) -> S:
        if not s["code"]:
            res = {"verdict": "RE", "time_ms": None, "memory_kb": None, "feedback": "No code block found."}
            log.warning("[graph] tentativa sem bloco de código, verdict=RE")
        else:
            log.info("[graph] enviando solução para submissão; attempt=%s", s["attempt"])
            res = submit_fn(s["problem"], s["code"])
            log.info("[graph] resultado da submissão: %s", res.get("verdict"))
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
