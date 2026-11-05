"""Caminhos padrão usados pelo projeto."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

FILTER_DIR = OUTPUTS_DIR / "01_filter"
DOWNLOAD_DIR = OUTPUTS_DIR / "02_download"
LOOP_DIR = OUTPUTS_DIR / "03_loop"
QODANA_DIR = OUTPUTS_DIR / "04_qodana"

DEFAULT_FILTERED_SUBMISSIONS = FILTER_DIR / "01_filter_filtered_submissions.csv"
DEFAULT_PROBLEMS_CSV = DOWNLOAD_DIR / "AtCoder" / "02_download_atcoder_submissions_problems.csv"
DEFAULT_LOOP_PROBLEMS_CSV = LOOP_DIR / "03_loop_problems.csv"
DEFAULT_LOOP_RESULTS_CSV = LOOP_DIR / "03_loop_resultados.csv"
DEFAULT_LOOP_SOLUTIONS_DIR = LOOP_DIR / "03_loop_solucoes"
DEFAULT_QODANA_REPORT = QODANA_DIR / "04_qodana_relatorio"
