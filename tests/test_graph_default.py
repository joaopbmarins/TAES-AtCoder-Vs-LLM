from taes.loop.engine.graphs.default import extract_code


def test_extract_code_prefers_last_python_block():
    response = (
        "```python\nprint('old')\n```\n"
        "```python\nprint('new')\n```"
    )

    assert extract_code(response) == "print('new')\n"


def test_extract_code_accepts_truncated_python_fence():
    assert extract_code("```python\nprint('ok')") == "print('ok')\n"


def test_extract_code_rejects_invalid_unfenced_text():
    assert extract_code("not valid python ???") == ""
