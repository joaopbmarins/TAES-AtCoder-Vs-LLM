from taes.core.models import Problem, Sample
from taes.core.paths import DEFAULT_LOOP_SOLUTIONS_DIR, PROJECT_ROOT


def test_sample_model_matches_scraper_shape():
    sample: Sample = ("input\n", "output\n")
    problem: Problem = {
        "id": "abc300_a",
        "contest": "abc300",
        "title": "Example",
        "statement": "Statement",
        "samples": [sample],
    }

    assert problem["samples"] == [("input\n", "output\n")]


def test_default_paths_are_repository_relative():
    assert PROJECT_ROOT.name == "TAES-AtCoder-Vs-LLM"
    assert DEFAULT_LOOP_SOLUTIONS_DIR == PROJECT_ROOT / "outputs" / "03_loop" / "03_loop_solucoes"
