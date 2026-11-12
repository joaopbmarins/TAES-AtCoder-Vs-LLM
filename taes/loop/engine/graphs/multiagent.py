"""Grafo multiagente: planejamento, código, testes, validação e submissão.

Agentes com LLM: Planner, Coder e Test Agent. Validator e Submission Manager são determinísticos.

Política de testes: os exemplos OFICIAIS do enunciado bloqueiam a submissão; os testes gerados pelo
Test Agent não têm gabarito (a saída esperada também vem do LLM), então só geram AVISO. Assim uma
solução correta nunca deixa de ser submetida por causa de um teste gerado errado.
"""
from __future__ import annotations

import json
import logging

from langgraph.graph import END, START, StateGraph

from ....core.config import FENCE, LOCAL_PRECHECK, MAX_ATTEMPTS, MAX_FEEDBACK_CHARS, MAX_VALIDATION_ATTEMPTS
from ...integrations.judge import Submitter
from ...integrations.llm import invoke_with_retry
from ...validation.local_check import check_samples
from .common import FENCE_RE, extract_code
from .state import S

log = logging.getLogger(__name__)

MAX_GENERATED_TESTS = 10
MAX_TEST_CHARS = 20_000
TEST_GENERATION_RETRIES = 2


def _problem_text(statement: str) -> str:
    return f'The coding problem:\n\n"""\n{statement}\n"""\n'


def build_planner_prompt(statement: str) -> str:
    return (
        "You are the Planner Agent. Analyze the competitive programming problem below. "
        "Describe the algorithm, correctness argument, complexity, and important edge cases. "
        "Do not write the final solution code.\n" + _problem_text(statement)
    )


def build_test_prompt(statement: str, plan: str = "") -> str:
    return (
        "You are the Test Agent. Create normal and extreme tests for the problem below. "
        f"Return only a JSON array with at most {MAX_GENERATED_TESTS} objects having exactly the keys "
        "`input` and `output`; both values must be strings. Keep every test small enough to write by hand "
        "and only include tests whose expected output you can compute with certainty.\n"
        + _problem_text(statement)
        + f"\nPlanner strategy:\n\"\"\"\n{plan}\n\"\"\"\n"
    )


def build_coder_prompt(statement: str, plan: str, feedback: str = "", previous_code: str = "") -> str:
    repair = ""
    if feedback or previous_code:
        repair = (
            "\nYour previous attempt failed. Fix it.\n"
            f"Feedback:\n\"\"\"\n{feedback[:MAX_FEEDBACK_CHARS]}\n\"\"\"\n"
        )
        if previous_code:
            repair += f"\nThe code with the error:\n\n{FENCE}python\n{previous_code}\n{FENCE}\n"
    return (
        "You are the Coder Agent. Implement the solution in Python 3 using the planner's strategy. "
        "Return only one Python code block. The program must read standard input and write standard output.\n"
        + _problem_text(statement)
        + f"Planner strategy:\n\"\"\"\n{plan}\n\"\"\"\n"
        + repair
        + f"\nUse this code block format:\n{FENCE}python\n{FENCE}\n"
    )


def parse_tests(text: str, samples: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Lê testes JSON do Test Agent; itens inválidos são ignorados e os exemplos ficam sempre na frente."""
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
    tests = [tuple(sample) for sample in samples]
    generated = 0
    for item in parsed:
        if generated >= MAX_GENERATED_TESTS:
            break
        if not isinstance(item, dict) or not isinstance(item.get("input"), str) or not isinstance(item.get("output"), str):
            continue
        if len(item["input"]) > MAX_TEST_CHARS or len(item["output"]) > MAX_TEST_CHARS:
            continue
        pair = (item["input"], item["output"])
        if pair not in tests:
            tests.append(pair)
            generated += 1
    return tests


def build_multiagent_graph(llm, submit_fn: Submitter, node_llms=None):
    node_llms = node_llms or {}
    planner_llm = node_llms.get("planner", llm)
    coder_llm = node_llms.get("coder", llm)
    test_llm = node_llms.get("test", llm)

    def planner(s: S) -> S:
        try:
            text = invoke_with_retry(planner_llm, build_planner_prompt(s["problem"]["statement"]))
        except Exception as exc:  # o Coder ainda consegue resolver sem plano
            log.warning("[graph] Planner falhou (%s); seguindo sem plano", exc)
            text = ""
        return {"plan": text}

    def test_agent(s: S) -> S:
        samples = list(s["problem"]["samples"])
        if not LOCAL_PRECHECK:
            return {"tests": samples}
        prompt = build_test_prompt(s["problem"]["statement"], s.get("plan", ""))
        tests = samples
        for retry in range(TEST_GENERATION_RETRIES + 1):
            try:
                # Retries intentionally reuse only the problem and plan. Candidate code and
                # prior test output are never supplied, avoiding confirmation bias.
                text = invoke_with_retry(test_llm, prompt)
                tests = parse_tests(text, samples)
                break
            except Exception as exc:
                log.warning("[graph] Test Agent inválido (tentativa %d/%d): %s",
                            retry + 1, TEST_GENERATION_RETRIES + 1, exc)
        else:
            log.warning("[graph] Test Agent esgotou as tentativas; usando apenas exemplos oficiais")
        return {"tests": tests}

    def coder(s: S) -> S:
        attempt = s.get("attempt", 0) + 1
        previous = s.get("result") or {}
        feedback = previous.get("feedback", "")
        prompt = build_coder_prompt(s["problem"]["statement"], s.get("plan", ""), feedback, s.get("code", ""))
        text = invoke_with_retry(coder_llm, prompt)
        code = extract_code(text)
        return {"prompt": prompt, "raw": text, "code": code, "attempt": attempt}

    def _entry(s: S, result: dict, **extra) -> dict:
        return {
            "attempt": s["attempt"], "prompt": s["prompt"], "raw_response": s["raw"],
            "code": s["code"], "result": result,
            "plan": s.get("plan", ""), "generated_tests": [list(t) for t in s.get("tests", [])[len(s["problem"]["samples"]):]],
            **extra,
        }

    def validator(s: S) -> S:
        validation_attempts = s.get("validation_attempts", 0) + 1
        samples = list(s["problem"]["samples"])
        warning = ""
        if not s["code"]:
            failure = {"verdict": "RE", "time_ms": None, "memory_kb": None, "feedback": "No code block found."}
        elif not LOCAL_PRECHECK:
            failure = None
        else:
            failure = check_samples(s["code"], samples)  # exemplos oficiais: bloqueiam
            if failure is None:
                extras = list(s.get("tests", samples))[len(samples):]
                extra_failure = check_samples(s["code"], extras) if extras else None
                if extra_failure is not None:
                    warning = ("Generated test failed (the expected output of generated tests may be wrong): "
                               + extra_failure["feedback"])
                    log.warning("[graph] teste gerado falhou, mas exemplos oficiais passaram; submetendo mesmo assim")

        if failure is not None:
            failure["source"] = "local"
            return {
                "result": failure,
                "validation_attempts": validation_attempts,
                "log": s.get("log", []) + [_entry(s, failure)],
            }

        passed = {"verdict": "LOCAL_AC", "time_ms": None, "memory_kb": None, "source": "local",
                  "feedback": warning or "Local tests passed."}
        log.info("[graph] Validator: exemplos oficiais passaram (aviso de teste gerado: %s)", bool(warning))
        return {"result": passed, "pending_warning": warning}

    def submission_manager(s: S) -> S:
        result = submit_fn(s["problem"], s["code"])
        result["source"] = "atcoder"
        submission_attempts = s.get("submission_attempts", 0) + 1
        warning = s.get("pending_warning", "")
        extra = {"local_warning": warning} if warning else {}
        if warning and result.get("verdict") != "AC":
            result["feedback"] = f"{result.get('feedback', '')}\n{warning}".strip()
        return {
            "result": result,
            "submissions": submission_attempts,
            "submission_attempts": submission_attempts,
            "validation_attempts": 0,
            "log": s.get("log", []) + [_entry(s, result, **extra)],
        }

    def after_validation(s: S) -> str:
        if s["result"]["verdict"] == "LOCAL_AC":
            return "submit"
        return "end" if s.get("validation_attempts", 0) >= MAX_VALIDATION_ATTEMPTS else "coder"

    def after_submission(s: S) -> str:
        return "end" if s["result"]["verdict"] == "AC" or s.get("submission_attempts", 0) >= MAX_ATTEMPTS else "coder"

    graph = StateGraph(S)
    graph.add_node("planner", planner)
    graph.add_node("test_agent", test_agent)
    graph.add_node("coder", coder)
    graph.add_node("validator", validator)
    graph.add_node("submission_manager", submission_manager)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "test_agent")
    graph.add_edge("planner", "coder")
    # Duas arestas separadas (não um join): na 1ª passada os dois ramos rodam no mesmo superstep e o
    # Validator roda uma vez; nas tentativas seguintes só o Coder roda, e um join esperaria o Test Agent.
    graph.add_edge("test_agent", "validator")
    graph.add_edge("coder", "validator")
    graph.add_conditional_edges("validator", after_validation, {"submit": "submission_manager", "coder": "coder", "end": END})
    graph.add_conditional_edges("submission_manager", after_submission, {"coder": "coder", "end": END})
    return graph.compile()
