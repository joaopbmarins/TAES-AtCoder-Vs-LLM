"""Grafo multiagente: planejamento, código, testes, validação e submissão."""
from __future__ import annotations

import json
import logging

from langgraph.graph import END, START, StateGraph

from ....core.config import FENCE, LOCAL_PRECHECK, MAX_ATTEMPTS, MAX_FEEDBACK_CHARS
from ...integrations.judge import Submitter
from ...integrations.llm import invoke_with_retry
from ...validation.local_check import check_samples
from .common import FENCE_RE, extract_code
from .state import S

log = logging.getLogger(__name__)


def _problem_text(statement: str) -> str:
    return f'The coding problem:\n\n"""\n{statement}\n"""\n'


def planner_prompt(statement: str) -> str:
    return (
        "You are the Planner Agent. Analyze the competitive programming problem below. "
        "Describe the algorithm, correctness argument, complexity, and important edge cases. "
        "Do not write the final solution code.\n" + _problem_text(statement)
    )


def test_prompt(statement: str, plan: str = "") -> str:
    return (
        "You are the Test Agent. Create normal and extreme tests for the problem below. "
        "Return only a JSON array of objects with exactly the keys `input` and `output`; "
        "both values must be strings. Include at least the examples when they are available.\n"
        + _problem_text(statement)
        + f"\nPlanner strategy:\n\"\"\"\n{plan}\n\"\"\"\n"
    )


def coder_prompt(statement: str, plan: str, feedback: str = "") -> str:
    feedback_text = (
        f"\nPrevious validation/submission feedback:\n\"\"\"\n{feedback[:MAX_FEEDBACK_CHARS]}\n\"\"\"\n"
        if feedback
        else ""
    )
    return (
        "You are the Coder Agent. Implement the solution in Python 3 using the planner's strategy. "
        "Return only one Python code block. The program must read standard input and write standard output.\n"
        + _problem_text(statement)
        + f"Planner strategy:\n\"\"\"\n{plan}\n\"\"\"\n"
        + feedback_text
        + f"Use this code block format:\n{FENCE}python\n{FENCE}\n"
    )


def parse_tests(text: str, samples: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Lê testes JSON do Test Agent e sempre mantém os exemplos como base."""
    candidates = [text]
    candidates.extend(code for _, code in FENCE_RE.findall(text or "") if code.strip())
    parsed = None
    for candidate in candidates:
        try:
            value = json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            parsed = value
            break
    if parsed is None:
        raise ValueError("Test Agent não retornou um JSON válido de testes.")
    tests = list(samples)
    for item in parsed:
        if not isinstance(item, dict) or not isinstance(item.get("input"), str) or not isinstance(item.get("output"), str):
            raise ValueError("Test Agent retornou um teste sem strings 'input' e 'output'.")
        pair = (item["input"], item["output"])
        if pair not in tests:
            tests.append(pair)
    return tests


def build_multiagent_graph(llm, submit_fn: Submitter):
    def planner(s: S) -> S:
        text = invoke_with_retry(llm, planner_prompt(s["problem"]["statement"]))
        return {"plan": text}

    def test_agent(s: S) -> S:
        text = invoke_with_retry(llm, test_prompt(s["problem"]["statement"], s.get("plan", "")))
        try:
            tests = parse_tests(text, s["problem"]["samples"])
        except ValueError as exc:
            log.warning("[graph] Test Agent inválido: %s", exc)
            tests = list(s["problem"]["samples"])
        return {"tests": tests}

    def coder(s: S) -> S:
        attempt = s.get("attempt", 0) + 1
        feedback = s.get("result", {}).get("feedback", "") if s.get("result") else ""
        prompt = coder_prompt(s["problem"]["statement"], s.get("plan", ""), feedback)
        text = invoke_with_retry(llm, prompt)
        code = extract_code(text)
        return {"prompt": prompt, "raw": text, "code": code, "attempt": attempt}

    def validator(s: S) -> S:
        if not s["code"]:
            result = {"verdict": "RE", "time_ms": None, "memory_kb": None, "feedback": "No code block found."}
        elif LOCAL_PRECHECK:
            result = check_samples(s["code"], s.get("tests", s["problem"]["samples"]))
            if result is None:
                result = {"verdict": "LOCAL_AC", "time_ms": None, "memory_kb": None, "feedback": "Local tests passed."}
                log.info("[graph] Validator Agent: todos os testes locais passaram")
        else:
            result = {"verdict": "LOCAL_AC", "time_ms": None, "memory_kb": None, "feedback": "Local validation skipped."}
        result["source"] = "local"
        entry = {
            "attempt": s["attempt"], "prompt": s["prompt"], "raw_response": s["raw"],
            "code": s["code"], "result": result,
        }
        return {"result": result, "log": s.get("log", []) + [entry]}

    def submission_manager(s: S) -> S:
        submissions = s.get("submissions", 0) + 1
        result = submit_fn(s["problem"], s["code"])
        result["source"] = "atcoder"
        entry = dict(s["log"][-1])
        entry["result"] = result
        return {"result": result, "submissions": submissions, "log": s["log"][:-1] + [entry]}

    def after_validation(s: S) -> str:
        return "submit" if s["result"]["verdict"] == "LOCAL_AC" else (
            "end" if s["attempt"] >= MAX_ATTEMPTS else "coder"
        )

    def after_submission(s: S) -> str:
        if s["result"]["verdict"] == "AC" or s["submissions"] >= MAX_ATTEMPTS:
            return "end"
        return "coder" if s["attempt"] < MAX_ATTEMPTS else "end"

    graph = StateGraph(S)
    graph.add_node("planner", planner)
    graph.add_node("test_agent", test_agent)
    graph.add_node("coder", coder)
    graph.add_node("validator", validator)
    graph.add_node("submission_manager", submission_manager)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "test_agent")
    graph.add_edge("planner", "coder")
    graph.add_edge("test_agent", "validator")
    graph.add_edge("coder", "validator")
    graph.add_conditional_edges("validator", after_validation, {"submit": "submission_manager", "coder": "coder", "end": END})
    graph.add_conditional_edges("submission_manager", after_submission, {"coder": "coder", "end": END})
    return graph.compile()
