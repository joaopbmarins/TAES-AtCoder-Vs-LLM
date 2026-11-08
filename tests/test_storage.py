import csv

from taes.storage.csv import load_previous, read_ids, write_results


def test_read_ids_deduplicates_without_reordering(tmp_path):
    source = tmp_path / "problems.csv"
    source.write_text("problem_id\nabc_a\nabc_a\nabc_b\n", encoding="utf-8")

    assert read_ids(str(source)) == ["abc_a", "abc_b"]


def test_write_results_round_trips_result_fields(tmp_path):
    output = tmp_path / "results.csv"
    rows = {
        "abc_a": {
            "problem_id": "abc_a",
            "verdict": "AC",
            "attempts": 1,
            "reason": "accepted",
            "feedback": "",
        }
    }

    write_results(str(output), rows)

    with output.open(encoding="utf-8", newline="") as stream:
        assert list(csv.DictReader(stream))[0]["verdict"] == "AC"
    assert load_previous(str(output))["abc_a"]["attempts"] == "1"
