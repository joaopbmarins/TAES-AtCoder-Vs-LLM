import pandas as pd
import pytest

from taes.atcoder import downloader


def test_download_submissions_supports_bounded_workers(tmp_path, monkeypatch):
    calls = []

    def fake_submission_data(contest_id, submission_id):
        calls.append(submission_id)
        return {
            "code": f"print({submission_id})\n",
            "contest_name": contest_id,
            "problem_name": "A",
            "exec_time_ms": 1,
            "memory_kb": 2,
        }

    monkeypatch.setattr(downloader, "get_submission_data", fake_submission_data)
    rows = pd.DataFrame(
        [
            {"id": 101, "contest_id": "abc300", "problem_id": "abc300_a", "language": "Python", "result": "AC"},
            {"id": 102, "contest_id": "abc300", "problem_id": "abc300_a", "language": "Python", "result": "AC"},
        ]
    )

    downloader.download_submissions_from_df(
        rows,
        output_dir=str(tmp_path / "out"),
        metadata_csv=str(tmp_path / "metadata.csv"),
        workers=2,
        delay=0,
    )
    downloader.download_submissions_from_df(
        rows,
        output_dir=str(tmp_path / "out"),
        metadata_csv=str(tmp_path / "metadata.csv"),
        workers=2,
        delay=0,
    )

    assert (tmp_path / "out" / "abc300" / "abc300_a" / "101_AC.py").exists()
    assert (tmp_path / "out" / "abc300" / "abc300_a" / "102_AC.py").exists()
    assert sorted(calls) == [101, 102]
    assert len(pd.read_csv(tmp_path / "metadata.csv")) == 2


@pytest.mark.parametrize("workers, delay", [(0, 0), (1, -1)])
def test_download_rejects_invalid_throttling(workers, delay, tmp_path):
    with pytest.raises(ValueError):
        downloader.download_submissions_from_df(
            pd.DataFrame(columns=["id", "contest_id", "problem_id", "language", "result"]),
            output_dir=str(tmp_path),
            workers=workers,
            delay=delay,
        )
