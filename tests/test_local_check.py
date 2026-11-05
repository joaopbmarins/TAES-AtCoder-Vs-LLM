from taes.loop.validation.local_check import check_samples


def test_check_samples_accepts_matching_output():
    code = "value = input().strip()\nprint(value)\n"

    assert check_samples(code, [("hello\n", "hello\n")]) is None


def test_check_samples_reports_wrong_answer():
    code = "print('wrong')\n"

    result = check_samples(code, [("input\n", "expected\n")])

    assert result is not None
    assert result["verdict"] == "WA"


def test_check_samples_reports_syntax_error():
    result = check_samples("print(\n", [])

    assert result is not None
    assert result["verdict"] == "CE"
