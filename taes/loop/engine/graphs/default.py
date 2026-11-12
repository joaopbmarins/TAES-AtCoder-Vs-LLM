"""Grafo padrão do projeto: build_prompt -> generate -> evaluate -> (reparo | fim)."""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from ....core.config import FENCE, LOCAL_PRECHECK, MAX_ATTEMPTS, MAX_FEEDBACK_CHARS, MAX_VALIDATION_ATTEMPTS
from ...integrations.judge import Submitter
from ...integrations.llm import invoke_with_retry
from ...validation.local_check import check_samples
from .common import extract_code
from .state import S

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
        validation_attempts = s.get("validation_attempts", 0) + 1
        entry = {
            "attempt": s["attempt"],
            "prompt": s["prompt"],
            "raw_response": s["raw"],
            "code": s["code"],
        }
        if not s["code"]:
            res = {"verdict": "RE", "time_ms": None, "memory_kb": None, "feedback": "No code block found."}
            log.warning("[graph] tentativa sem bloco de código, verdict=RE")
        else:
            res = check_samples(s["code"], s["problem"]["samples"]) if LOCAL_PRECHECK else None
            if res is not None:
                res["source"] = "local"
                log.info("[graph] falhou na checagem local: %s (não submetido)", res["verdict"])
                return {
                    "result": res,
                    "validation_attempts": validation_attempts,
                    "log": s.get("log", []) + [{**entry, "result": res}],
                }
            else:
                log.info("[graph] enviando solução para submissão; attempt=%s", s["attempt"])
                res = submit_fn(s["problem"], s["code"])
                res["source"] = "atcoder"
                submission_attempts = s.get("submission_attempts", 0) + 1
                log.info("[graph] resultado da submissão: %s", res.get("verdict"))
                return {
                    "result": res,
                    "submission_attempts": submission_attempts,
                    "validation_attempts": 0,
                    "log": s.get("log", []) + [{**entry, "result": res}],
                }
        return {
            "result": res,
            "validation_attempts": validation_attempts,
            "log": s.get("log", []) + [{**entry, "result": res}],
        }

    def route(s: S) -> str:
        done = (
            s["result"]["verdict"] == "AC"
            or s.get("submission_attempts", 0) >= MAX_ATTEMPTS
            or s.get("validation_attempts", 0) >= MAX_VALIDATION_ATTEMPTS
        )
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
