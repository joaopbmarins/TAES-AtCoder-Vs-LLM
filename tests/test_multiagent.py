import json

import pytest

pytest.importorskip("langgraph")

from taes.loop.engine.graphs.multiagent import (  # noqa: E402
    build_coder_prompt,
    build_multiagent_graph,
    parse_tests,
)

SAMPLES = [("2\n", "4")]


def test_parse_tests_keeps_samples_first_and_skips_invalid_items():
    text = json.dumps([{"input": "3\n", "output": "6"}, {"input": 1, "output": "x"}, "lixo"])
    assert parse_tests(text, SAMPLES) == [("2\n", "4"), ("3\n", "6")]


def test_parse_tests_accepts_fenced_json_and_rejects_non_json():
    assert parse_tests('```json\n[{"input": "5\\n", "output": "10"}]\n```', SAMPLES)[-1] == ("5\n", "10")
    with pytest.raises(ValueError):
        parse_tests("sem json", SAMPLES)


def test_coder_prompt_includes_previous_code_on_repair():
    prompt = build_coder_prompt("stmt", "plan", "WA", "print(1)")
    assert "print(1)" in prompt and "WA" in prompt
    assert "previous attempt" not in build_coder_prompt("stmt", "plan")


class FakeLLM:
    def __init__(self, coder_codes, tests="[]"):
        self.coder_codes = list(coder_codes)
        self.tests = tests

    def invoke(self, prompt):
        class R:
            usage_metadata = {}
        r = R()
        if "Planner Agent" in prompt:
            r.content = "plan"
        elif "Test Agent" in prompt:
            r.content = self.tests
        else:
            r.content = f"```python\n{self.coder_codes.pop(0)}\n```"
        return r


class TaggedLLM(FakeLLM):
    def __init__(self, tag, coder_codes=None, tests="[]"):
        super().__init__(coder_codes or ["print(int(input()) * 2)"], tests)
        self.tag = tag
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        response = super().invoke(prompt)
        response.content = f"{self.tag}:{response.content}"
        if "Test Agent" in prompt:
            response.content = self.tests
        return response


def _run(llm, submit):
    graph = build_multiagent_graph(llm, submit)
    problem = {"id": "x_a", "contest": "x", "title": "", "statement": "s", "samples": SAMPLES}
    return graph.invoke({"problem": problem}, config={"recursion_limit": 100})


def test_wrong_generated_test_does_not_block_submission():
    bad_tests = json.dumps([{"input": "3\n", "output": "999"}])  # gabarito errado
    submitted = []

    def submit(problem, code):
        submitted.append(code)
        return {"verdict": "AC", "time_ms": 1, "memory_kb": 1, "feedback": ""}

    final = _run(FakeLLM(["print(int(input()) * 2)"], bad_tests), submit)
    assert submitted and final["result"]["verdict"] == "AC"
    assert final["log"][-1]["result"]["source"] == "atcoder"
    assert final["log"][-1]["local_warning"]


def test_official_sample_failure_blocks_submission_and_retries():
    submitted = []

    def submit(problem, code):
        submitted.append(code)
        return {"verdict": "AC", "time_ms": 1, "memory_kb": 1, "feedback": ""}

    final = _run(FakeLLM(["print(0)", "print(int(input()) * 2)"]), submit)
    assert len(submitted) == 1 and final["attempt"] == 2
    assert final["submission_attempts"] == 1
    assert final["validation_attempts"] == 0
    assert [e["result"]["source"] for e in final["log"]] == ["local", "atcoder"]


def test_submission_limit_counts_atcoder_submissions_not_local_generations():
    submitted = []

    def submit(problem, code):
        submitted.append(code)
        return {"verdict": "WA", "time_ms": 1, "memory_kb": 1, "feedback": "wrong"}

    final = _run(FakeLLM(["print(int(input()) * 2)"] * 3), submit)
    assert len(submitted) == 3
    assert final["submission_attempts"] == 3
    assert final["validation_attempts"] == 0


def test_multiagent_routes_each_llm_node_independently():
    planner = TaggedLLM("planner")
    coder = TaggedLLM("coder")
    test_agent = TaggedLLM("test", tests="[]")
    submitted = []

    def submit(problem, code):
        submitted.append(code)
        return {"verdict": "AC", "time_ms": 1, "memory_kb": 1, "feedback": ""}

    problem = {"id": "x_a", "contest": "x", "title": "", "statement": "s", "samples": SAMPLES}
    graph = build_multiagent_graph(
        TaggedLLM("unused"),
        submit,
        node_llms={"planner": planner, "coder": coder, "test": test_agent},
    )
    graph.invoke({"problem": problem}, config={"recursion_limit": 100})

    assert planner.prompts and "Planner Agent" in planner.prompts[0]
    assert coder.prompts and "Coder Agent" in coder.prompts[0]
    assert test_agent.prompts and "Test Agent" in test_agent.prompts[0]
    assert [code.strip() for code in submitted] == ["print(int(input()) * 2)"]


def test_test_agent_retries_invalid_generation_without_candidate_context():
    test_agent = TaggedLLM("test", tests="not json")
    coder = TaggedLLM("coder")
    planner = TaggedLLM("planner")
    submitted = []

    def submit(problem, code):
        submitted.append(code)
        return {"verdict": "AC", "time_ms": 1, "memory_kb": 1, "feedback": ""}

    problem = {"id": "x_a", "contest": "x", "title": "", "statement": "s", "samples": SAMPLES}
    graph = build_multiagent_graph(
        TaggedLLM("unused"),
        submit,
        node_llms={"planner": planner, "coder": coder, "test": test_agent},
    )
    graph.invoke({"problem": problem}, config={"recursion_limit": 100})

    assert len(test_agent.prompts) == 3
    assert all("print" not in prompt for prompt in test_agent.prompts)
    assert submitted
