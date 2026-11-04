#!/usr/bin/env python3
"""Orquestra a pipeline completa do TAES.

CSV uniforme ao longo da pipeline:
  - submissions.csv (dataset bruto do AtCoder Problems)
  - outputs/01_filter/01_filter_filtered_submissions.csv (saída do filtro)
  - outputs/03_loop/03_loop_problems.csv (lista de problem_id a resolver)
  - outputs/03_loop/03_loop_resultados.csv (saída do loop de geração)

Cada etapa pode ser executada isoladamente ou em sequência com:
  python taes_pipeline.py all --raw-csv submissions.csv --out-dir pipeline
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

import pandas as pd

from FiltroSubmissions import processar
from atCoder_downloader import download_submissions_from_df, export_problem_list_csv
from atcoder_loop.cli import main as run_loop_cli
from qodana_atcoder import main as run_qodana_cli


def export_problem_ids(input_csv: str | Path, out_csv: str | Path) -> str:
    df = pd.read_csv(input_csv)
    if "problem_id" not in df.columns:
        raise ValueError(f"CSV '{input_csv}' não contém a coluna 'problem_id'.")
    ids = df["problem_id"].dropna().astype(str).str.strip()
    ids = ids[ids.ne("")].drop_duplicates()
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"problem_id": ids.tolist()}).to_csv(out, index=False)
    return str(out)


def run_filter_stage(raw_csv: str | Path, out_csv: str | Path, **kwargs) -> str:
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    processar(
        saida=str(out),
        dataset_path=str(raw_csv),
        **kwargs,
    )
    return str(out)


def run_download_stage(input_csv: str | Path, output_dir: str | Path, *, all_results: bool = False) -> str:
    input_path = Path(input_csv)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path)
    if "id" not in df.columns:
        raise ValueError(f"CSV '{input_csv}' não contém a coluna 'id'. O download precisa de id, contest_id, problem_id, language e result.")

    metadata_csv = output_path / "02_download_atcoder_submissions_metadata.csv"
    download_submissions_from_df(
        df,
        output_dir=str(output_path),
        only_ac=not all_results,
        metadata_csv=str(metadata_csv),
    )
    export_problem_list_csv(str(metadata_csv), str(output_path / "02_download_atcoder_submissions_problems.csv"))
    return str(metadata_csv)


def prepare_ai_layout(results_csv: str | Path, from_dir: str | Path, target_root: str | Path) -> Path:
    results_path = Path(results_csv)
    source_dir = Path(from_dir)
    target_root = Path(target_root)
    if not results_path.exists():
        raise FileNotFoundError(f"CSV de resultados não encontrado: {results_path}")

    with results_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    for row in rows:
        verdict = (row.get("verdict") or "").strip()
        pid = (row.get("problem_id") or "").strip()
        if not pid or verdict != "AC":
            continue
        candidates = sorted(source_dir.glob(f"{pid}.*"))
        if not candidates:
            continue
        chosen = candidates[0]
        contest = pid.rsplit("_", 1)[0]
        target = target_root / contest / pid / chosen.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(chosen, target)
    return target_root


def run_loop_stage(input_csv: str | Path, *, out_csv: str | Path, out_dir: str | Path, **kwargs) -> str:
    path = Path(out_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    cli_args = [
        str(input_csv),
        "--out",
        str(path),
        "--out-dir",
        str(out_dir),
    ]
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                cli_args.append(f"--{key.replace('_', '-')}")
            continue
        cli_args.extend([f"--{key.replace('_', '-')}", str(value)])
    run_loop_cli(cli_args)
    return str(path)


def run_qodana_stage(root: str | Path, *, out: str | Path = str(Path("outputs") / "04_qodana" / "04_qodana_relatorio"), rules_python: str | Path | None = None,
                     rules_cpp: str | Path | None = None, source_labels: str = "AtCoder=humano,IA=IA",
                     linter_python: str = "jetbrains/qodana-python-community:2026.2",
                     linter_cpp: str = "jetbrains/qodana-clang:2026.2") -> str:
    argv = [str(root), "--sources", source_labels, "--out", str(out)]
    if rules_python is not None:
        argv.extend(["--rules-python", str(rules_python)])
    if rules_cpp is not None:
        argv.extend(["--rules-cpp", str(rules_cpp)])
    if linter_python:
        argv.extend(["--linter-python", linter_python])
    if linter_cpp:
        argv.extend(["--linter-cpp", linter_cpp])
    run_qodana_cli(argv)
    return str(out)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Integração da pipeline do TAES.")
    sub = ap.add_subparsers(dest="stage", required=True)

    filter_p = sub.add_parser("filter", help="Filtra o dataset bruto em um CSV uniforme.")
    filter_p.add_argument("--csv", default="submissions.csv", help="Dataset bruto do AtCoder Problems.")
    filter_p.add_argument("--out", default=str(Path("outputs") / "01_filter" / "01_filter_filtered_submissions.csv"), help="CSV de saída filtrado.")
    filter_p.add_argument("--contests", nargs="*", help="Ex.: abc300 abc301")
    filter_p.add_argument("--prefixos-contest", nargs="*", help="Ex.: abc arc")
    filter_p.add_argument("--linguagens", nargs="*", help="Ex.: Python PyPy")
    filter_p.add_argument("--linguagens-exatas", nargs="*")
    filter_p.add_argument("--resultados", nargs="*", help="Ex.: AC WA")
    filter_p.add_argument("--all-results", action="store_true")
    filter_p.add_argument("--corte")
    filter_p.add_argument("--envio-de")
    filter_p.add_argument("--envio-ate")

    download_p = sub.add_parser("download", help="Baixa os códigos das submissões filtradas.")
    download_p.add_argument("--input", default=str(Path("outputs") / "01_filter" / "01_filter_filtered_submissions.csv"), help="CSV filtrado de entrada.")
    download_p.add_argument("--out", default=str(Path("outputs") / "02_download" / "02_download_atcoder_submissions"), help="Pasta da árvore de submissões humanas.")
    download_p.add_argument("--all-results", action="store_true", help="Baixa também RE/WA/TLE etc.")

    problem_p = sub.add_parser("problems", help="Exporta uma lista de problem_id a partir de um CSV de entrada.")
    problem_p.add_argument("--input", default=str(Path("outputs") / "01_filter" / "01_filter_filtered_submissions.csv"), help="CSV com a coluna problem_id.")
    problem_p.add_argument("--out", default=str(Path("outputs") / "03_loop" / "03_loop_problems.csv"), help="Arquivo de saída com problem_id.")

    loop_p = sub.add_parser("loop", help="Executa o loop de geração/resolução dos problemas.")
    loop_p.add_argument("--input", default=str(Path("outputs") / "03_loop" / "03_loop_problems.csv"), help="CSV com a coluna problem_id.")
    loop_p.add_argument("--out", default=str(Path("outputs") / "03_loop" / "03_loop_resultados.csv"), help="CSV de saída do loop.")
    loop_p.add_argument("--out-dir", default=str(Path("outputs") / "03_loop" / "03_loop_solucoes"), help="Diretório para salvar as soluções.")
    loop_p.add_argument("--provider", choices=["openai", "google", "nvidia"], default="google")
    loop_p.add_argument("--model", default="gemini-3.8-flash")
    loop_p.add_argument("--temperature", type=float, default=1.0)
    loop_p.add_argument("--max-tokens", type=int, default=4096)
    loop_p.add_argument("--no-resume", action="store_true")

    qodana_p = sub.add_parser("qodana", help="Executa a comparação Qodana entre código humano e IA.")
    qodana_p.add_argument("--root", default=str(Path("outputs") / "02_download" / "02_download_atcoder_submissions"), help="Pasta raiz com AtCoder/ e IA/.")
    qodana_p.add_argument("--out", default=str(Path("outputs") / "04_qodana" / "04_qodana_relatorio"), help="Prefixo dos CSVs de saída do Qodana.")
    qodana_p.add_argument("--rules-python", type=str, help="Arquivo de regras Python.")
    qodana_p.add_argument("--rules-cpp", type=str, help="Arquivo de regras C/C++.")
    qodana_p.add_argument("--linter-python", default="jetbrains/qodana-python-community:2026.2")
    qodana_p.add_argument("--linter-cpp", default="jetbrains/qodana-clang:2026.2")
    qodana_p.add_argument("--sources", default="AtCoder=humano,IA=IA")

    all_p = sub.add_parser("all", help="Executa filter + download + loop em sequência e opcionalmente Qodana.")
    all_p.add_argument("--raw-csv", default="submissions.csv", help="Dataset bruto do AtCoder Problems.")
    all_p.add_argument("--out-dir", default=str(Path("outputs") / "00_pipeline"), help="Pasta de trabalho para a pipeline inteira.")
    all_p.add_argument("--contests", nargs="*")
    all_p.add_argument("--prefixos-contest", nargs="*")
    all_p.add_argument("--linguagens", nargs="*")
    all_p.add_argument("--linguagens-exatas", nargs="*")
    all_p.add_argument("--resultados", nargs="*")
    all_p.add_argument("--all-results", action="store_true")
    all_p.add_argument("--corte")
    all_p.add_argument("--envio-de")
    all_p.add_argument("--envio-ate")
    all_p.add_argument("--loop-provider", choices=["openai", "google", "nvidia"], default="openai")
    all_p.add_argument("--loop-model", default="gpt-4o-2024-05-13")
    all_p.add_argument("--loop-temperature", type=float, default=1.0)
    all_p.add_argument("--loop-max-tokens", type=int, default=4096)
    all_p.add_argument("--no-loop-resume", action="store_true")
    all_p.add_argument("--with-qodana", action="store_true", help="Roda também a análise Qodana ao fim.")
    all_p.add_argument("--rules-python", type=str, help="Arquivo de regras Python para o Qodana.")
    all_p.add_argument("--rules-cpp", type=str, help="Arquivo de regras C/C++ para o Qodana.")
    all_p.add_argument("--linter-python", default="jetbrains/qodana-python-community:2026.2")
    all_p.add_argument("--linter-cpp", default="jetbrains/qodana-clang:2026.2")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.stage == "filter":
        run_filter_stage(
            args.csv,
            args.out,
            contests_lista=args.contests,
            prefixos_contest=args.prefixos_contest,
            linguagens=args.linguagens,
            linguagens_exatas=args.linguagens_exatas,
            resultados=None if args.all_results else (args.resultados or ["AC"]),
            corte=args.corte,
            envio_de=args.envio_de,
            envio_ate=args.envio_ate,
        )
        return 0

    if args.stage == "download":
        run_download_stage(args.input, args.out, all_results=args.all_results)
        return 0

    if args.stage == "problems":
        export_problem_ids(args.input, args.out)
        return 0

    if args.stage == "loop":
        run_loop_stage(
            args.input,
            out_csv=args.out,
            out_dir=args.out_dir,
            provider=args.provider,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            no_resume=args.no_resume,
        )
        return 0

    if args.stage == "qodana":
        run_qodana_stage(
            root=args.root,
            out=args.out,
            rules_python=args.rules_python,
            rules_cpp=args.rules_cpp,
            source_labels=args.sources,
            linter_python=args.linter_python,
            linter_cpp=args.linter_cpp,
        )
        return 0

    if args.stage == "all":
        workspace = Path(args.out_dir)
        workspace.mkdir(parents=True, exist_ok=True)

        filter_dir = workspace / "01_filter"
        filter_dir.mkdir(parents=True, exist_ok=True)
        filtered_csv = filter_dir / "01_filter_filtered_submissions.csv"
        run_filter_stage(
            args.raw_csv,
            filtered_csv,
            contests_lista=args.contests,
            prefixos_contest=args.prefixos_contest,
            linguagens=args.linguagens,
            linguagens_exatas=args.linguagens_exatas,
            resultados=None if args.all_results else (args.resultados or ["AC"]),
            corte=args.corte,
            envio_de=args.envio_de,
            envio_ate=args.envio_ate,
        )

        download_dir = workspace / "02_download" / "AtCoder"
        download_dir.mkdir(parents=True, exist_ok=True)
        run_download_stage(filtered_csv, download_dir, all_results=args.all_results)

        loop_dir = workspace / "03_loop"
        loop_dir.mkdir(parents=True, exist_ok=True)
        problems_csv = loop_dir / "03_loop_problems.csv"
        export_problem_ids(filtered_csv, problems_csv)

        loop_out = loop_dir / "03_loop_resultados.csv"
        solutions_dir = loop_dir / "03_loop_solucoes"
        run_loop_stage(
            problems_csv,
            out_csv=loop_out,
            out_dir=solutions_dir,
            provider=args.loop_provider,
            model=args.loop_model,
            temperature=args.loop_temperature,
            max_tokens=args.loop_max_tokens,
            no_resume=args.no_loop_resume,
        )

        prepare_ai_layout(loop_out, solutions_dir, workspace / "02_download" / "IA")

        if args.with_qodana:
            qodana_dir = workspace / "04_qodana"
            qodana_dir.mkdir(parents=True, exist_ok=True)
            run_qodana_stage(
                root=workspace / "02_download",
                out=qodana_dir / "04_qodana_relatorio",
                rules_python=args.rules_python,
                rules_cpp=args.rules_cpp,
                source_labels="AtCoder=humano,IA=IA",
                linter_python=args.linter_python,
                linter_cpp=args.linter_cpp,
            )
        print(f"Pipeline concluída. Saída em: {workspace}")
        return 0

    raise ValueError(f"Etapa desconhecida: {args.stage}")


if __name__ == "__main__":
    raise SystemExit(main())
