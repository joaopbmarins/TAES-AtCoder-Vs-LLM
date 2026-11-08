"""Interface de linha de comando."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from ..core.paths import DEFAULT_LOOP_RESULTS_CSV, DEFAULT_LOOP_SOLUTIONS_DIR, DEFAULT_PROBLEMS_CSV, PROJECT_ROOT
from .engine.runner import run
from .integrations.judge import submit_atcoder
from .integrations.llm import build_llm

log = logging.getLogger("taes.loop")

DESCRIPTION = """CSV de ids -> scraping no AtCoder -> loop gerar/submeter/reparar.

CSV: uma coluna `problem_id` (ex.: abc300_a). O contest é o trecho antes do último "_".
Se nenhum CSV for informado, o programa usa o arquivo de problemas da etapa 2 por padrão.
Chaves de API: GOOGLE_API_KEY, OPENAI_API_KEY ou NVIDIA_API_KEY (pode usar um arquivo .env).
"""


def main(argv: list[str] | None = None) -> None:
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
    ap = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "csv",
        nargs="?",
        default=str(DEFAULT_PROBLEMS_CSV),
        help="CSV com a coluna problem_id; padrão: %(default)s",
    )
    ap.add_argument("--out", default=str(DEFAULT_LOOP_RESULTS_CSV))
    ap.add_argument(
        "--out-errors",
        default=None,
        help="CSV separado para problemas com erro/WA/TLE/RE; padrão: <out>_erros.csv",
    )
    ap.add_argument("--out-dir", default=str(DEFAULT_LOOP_SOLUTIONS_DIR))
    ap.add_argument("--provider", choices=["openai", "google", "nvidia"], default="google")
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--atcoder-session-cookie", help="Cookie/jar de sessão já autenticada do AtCoder.")
    ap.add_argument("--graph", default=None, help="grafo a usar (padrão: GRAPH_NAME de config.py)")
    ap.add_argument("--no-resume", action="store_true", help="refaz também os problemas já resolvidos")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    out_csv = Path(a.out)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_errors = Path(a.out_errors) if a.out_errors else out_csv.with_name(f"{out_csv.stem}_erros.csv")
    out_errors.parent.mkdir(parents=True, exist_ok=True)
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    llm = build_llm(a.provider, a.model, a.temperature, a.max_tokens)
    def submit_fn(problem, code):
        return submit_atcoder(problem, code, session_cookie=a.atcoder_session_cookie)
    rows = run(a.csv, str(out_csv), llm, submit_fn=submit_fn, out_dir=str(out_dir), resume=not a.no_resume,
               graph_name=a.graph, err_csv=str(out_errors))
    ac = sum(r["verdict"] == "AC" for r in rows)
    log.info("Concluído: %d/%d AC", ac, len(rows))


if __name__ == "__main__":
    main()
