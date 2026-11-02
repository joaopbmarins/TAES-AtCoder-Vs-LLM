import argparse
import os
from pathlib import Path

import pandas as pd
import requests

SUBS_URL = "https://s3-ap-northeast-1.amazonaws.com/kenkoooo/submissions.csv.gz"
SUBS_CANDIDATOS = ["submissions.csv", "submissions.csv.gz"]
CONTESTS = "https://kenkoooo.com/atcoder/resources/contests.json"
TZ = "America/Sao_Paulo"
DEFAULT_OUTPUT_DIR = "outputs/01_filter"
DEFAULT_FILTERED_FILENAME = "01_filter_filtered_submissions.csv"


def garantir_dataset(candidatos=SUBS_CANDIDATOS, url=SUBS_URL):
    """Devolve o caminho do dataset local; baixa o .csv.gz se nenhum existir."""
    for caminho in candidatos:
        if os.path.exists(caminho):
            print(f"Dataset encontrado: {caminho}")
            return caminho

    destino = "submissions.csv.gz"
    parcial = destino + ".part"          # evita deixar arquivo corrompido se o download cair
    print(f"Dataset não encontrado. Baixando para {destino} ...")

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        baixado = 0
        with open(parcial, "wb") as f:
            for pedaco in r.iter_content(chunk_size=1024 * 1024):
                f.write(pedaco)
                baixado += len(pedaco)
                if total:
                    print(f"\r  {baixado / 1e6:.0f}/{total / 1e6:.0f} MB "
                          f"({baixado / total:.0%})", end="", flush=True)
    print()
    os.replace(parcial, destino)         # só vira o arquivo final se terminou
    print("Download concluído.")
    return destino


def para_epoch(valor, fim=False):
    """Converte 'YYYY-MM-DD' ou 'YYYY-MM-DD HH:MM[:SS]' (fuso TZ) em epoch.
    Se for só data e fim=True, devolve o início do dia SEGUINTE (limite exclusivo),
    para que o último dia da janela entre inteiro."""
    ts = pd.Timestamp(valor)
    ts = ts.tz_localize(TZ) if ts.tzinfo is None else ts.tz_convert(TZ)
    so_data = isinstance(valor, str) and len(valor.strip()) <= 10
    if fim and so_data:
        ts += pd.Timedelta(days=1)
    return int(ts.timestamp())


contests = pd.DataFrame(requests.get(CONTESTS).json())
inicio = (contests[["id", "start_epoch_second"]]
          .rename(columns={"id": "contest_id",
                           "start_epoch_second": "contest_start_epoch"}))


def _prioridade_resultado(valor):
    """Prioridade para ordenar submissões úteis antes de aplicar caps."""
    if pd.isna(valor):
        return 99
    texto = str(valor).strip().upper()
    ordem = {"AC": 0, "WA": 1, "TLE": 2, "RE": 3, "CE": 4, "MLE": 5, "OLE": 6, "QLE": 7}
    return ordem.get(texto, 99)


def _aplicar_caps(df, max_por_problema=None, max_por_contest=None):
    """Aplica deduplicação por usuário/problema e limita o número de linhas."""
    if df.empty:
        return df

    df = df.copy()

    if "result" in df.columns:
        df["_resultado_ordem"] = df["result"].map(_prioridade_resultado)
    else:
        df["_resultado_ordem"] = 99

    if {"contest_id", "problem_id", "user_id"}.issubset(df.columns):
        df = df.sort_values(
            ["contest_id", "problem_id", "user_id", "_resultado_ordem", "epoch_second"],
            ascending=[True, True, True, True, True],
            kind="mergesort",
        )
        df = df.drop_duplicates(subset=["contest_id", "problem_id", "user_id"], keep="first")

    if max_por_problema is not None and {"contest_id", "problem_id"}.issubset(df.columns):
        df = df.sort_values(
            ["contest_id", "problem_id", "_resultado_ordem", "epoch_second"],
            ascending=[True, True, True, True],
            kind="mergesort",
        )
        df = df.groupby(["contest_id", "problem_id"], group_keys=False).head(max_por_problema)

    if max_por_contest is not None and "contest_id" in df.columns:
        df = df.sort_values(
            ["contest_id", "_resultado_ordem", "epoch_second"],
            ascending=[True, True, True],
            kind="mergesort",
        )
        df = df.groupby("contest_id", group_keys=False).head(max_por_contest)

    return df.drop(columns=["_resultado_ordem"], errors="ignore")


def processar(
    contests_lista=None,      # ex.: ["abc300", "abc301", "arc160"]
    prefixos_contest=None,    # ex.: ["abc", "arc"]  (todos os ABC e ARC)
    linguagens=None,          # ex.: ["C++", "Python"] (começa com...)
    linguagens_exatas=None,   # ex.: ["C++ 20 (gcc 12.2)"]
    resultados=["AC"],       # padrão: só aprovadas; use None para manter todos
    corte=None,               # "YYYY-MM-DD" (início do contest)
    envio_de=None,            # início da janela de envio: "YYYY-MM-DD" ou "YYYY-MM-DD HH:MM"
    envio_ate=None,           # fim da janela de envio (inclusivo se for só data)
    max_por_problema=None,    # no máximo de submissões por contest+problem
    max_por_contest=None,     # no máximo de submissões por contest
    saida=str(Path(DEFAULT_OUTPUT_DIR) / DEFAULT_FILTERED_FILENAME),
    dataset_path=None,
):
    if max_por_problema is not None and max_por_problema <= 0:
        raise ValueError("max_por_problema deve ser maior que zero.")
    if max_por_contest is not None and max_por_contest <= 0:
        raise ValueError("max_por_contest deve ser maior que zero.")

    subs = dataset_path if dataset_path is not None else garantir_dataset()  # .csv ou .csv.gz; baixa se faltar

    # evita sobrar arquivo antigo de uma execução anterior
    saida_path = Path(saida)
    saida_path.parent.mkdir(parents=True, exist_ok=True)
    if saida_path.exists():
        saida_path.unlink()

    corte_epoch = pd.Timestamp(corte, tz=TZ).timestamp() if corte else None
    envio_de_epoch = para_epoch(envio_de) if envio_de else None
    envio_ate_epoch = para_epoch(envio_ate, fim=True) if envio_ate else None   # exclusivo

    if envio_de_epoch and envio_ate_epoch and envio_de_epoch >= envio_ate_epoch:
        raise ValueError("envio_de deve ser anterior a envio_ate.")

    blocos = []
    for bloco in pd.read_csv(subs, chunksize=1_000_000):   # pandas detecta o .gz pela extensão
        # filtros baratos primeiro
        if envio_de_epoch is not None:
            bloco = bloco[bloco["epoch_second"] >= envio_de_epoch]
        if envio_ate_epoch is not None:
            bloco = bloco[bloco["epoch_second"] < envio_ate_epoch]
        if contests_lista:
            bloco = bloco[bloco["contest_id"].isin(contests_lista)]
        if prefixos_contest:
            bloco = bloco[bloco["contest_id"].str.startswith(tuple(prefixos_contest), na=False)]
        if linguagens:
            bloco = bloco[bloco["language"].str.startswith(tuple(linguagens), na=False)]
        if linguagens_exatas:
            bloco = bloco[bloco["language"].isin(linguagens_exatas)]
        if resultados:
            bloco = bloco[bloco["result"].isin(resultados)]
        if bloco.empty:
            continue

        bloco = bloco.merge(inicio, on="contest_id", how="left")
        if corte_epoch is not None:
            bloco = bloco[bloco["contest_start_epoch"] >= corte_epoch]
        if bloco.empty:
            continue

        bloco["submission_datetime"] = (
            pd.to_datetime(bloco["epoch_second"], unit="s", utc=True)
              .dt.tz_convert(TZ))
        bloco["contest_start_datetime"] = (
            pd.to_datetime(bloco["contest_start_epoch"], unit="s", utc=True)
              .dt.tz_convert(TZ))
        blocos.append(bloco)

    if not blocos:
        print(f"Nenhuma submissão passou nos filtros ({saida} não foi criado).")
        return saida

    final = pd.concat(blocos, ignore_index=True)
    if max_por_problema is not None or max_por_contest is not None:
        final = _aplicar_caps(final, max_por_problema=max_por_problema, max_por_contest=max_por_contest)

    final.to_csv(saida, index=False)
    print(f"Gerado: {saida}")
    return saida


def build_parser():
    ap = argparse.ArgumentParser(description="Filtra o dataset de submissions do AtCoder.")
    ap.add_argument("--csv", default="submissions.csv", help="Dataset bruto de submissões (opcional).")
    ap.add_argument("--out", default=str(Path(DEFAULT_OUTPUT_DIR) / DEFAULT_FILTERED_FILENAME),
                    help="CSV de saída filtrado.")
    ap.add_argument("--contests", nargs="*", help="IDs exatos de contests a manter, ex.: abc300 abc301")
    ap.add_argument("--prefixos-contest", nargs="*", help="Prefixos de contest, ex.: abc arc")
    ap.add_argument("--linguagens", nargs="*", help="Linguagens iniciais, ex.: Python PyPy")
    ap.add_argument("--linguagens-exatas", nargs="*", help="Nomes exatos de linguagens, ex.: 'C++ 20 (gcc 12.2)'")
    ap.add_argument("--resultados", nargs="*", help="Resultados a manter, ex.: AC WA. Se não informar, usa AC.")
    ap.add_argument("--all-results", action="store_true", help="Mantém todos os resultados sem filtrar por AC.")
    ap.add_argument("--corte", help="Mantém só contests iniciados a partir desta data (YYYY-MM-DD).")
    ap.add_argument("--envio-de", help="Limite inferior da janela de envio (YYYY-MM-DD ou YYYY-MM-DD HH:MM).")
    ap.add_argument("--envio-ate", help="Limite superior da janela de envio (YYYY-MM-DD ou YYYY-MM-DD HH:MM).")
    ap.add_argument("--max-por-problema", type=int, help="Mantém no máximo N submissões por contest+problem (ex.: 10).")
    ap.add_argument("--max-por-contest", type=int, help="Mantém no máximo N submissões por contest (ex.: 100).")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    resultados = None if args.all_results else (args.resultados or ["AC"])
    processar(
        contests_lista=args.contests,
        prefixos_contest=args.prefixos_contest,
        linguagens=args.linguagens,
        linguagens_exatas=args.linguagens_exatas,
        resultados=resultados,
        corte=args.corte,
        envio_de=args.envio_de,
        envio_ate=args.envio_ate,
        max_por_problema=args.max_por_problema,
        max_por_contest=args.max_por_contest,
        saida=args.out,
        dataset_path=args.csv,
    )
    return args.out


if __name__ == "__main__":
    main()