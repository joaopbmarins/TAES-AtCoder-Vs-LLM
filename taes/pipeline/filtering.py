import argparse
import os
import time
from pathlib import Path

import pandas as pd
import requests

from taes.core.files import atomic_replace

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
    parcial = destino + ".part"
    parcial_path = Path(parcial)
    offset = parcial_path.stat().st_size if parcial_path.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    if offset:
        print(f"Download interrompido encontrado. Retomando em {offset / 1e6:.0f} MB ...")
    else:
        print(f"Dataset não encontrado. Baixando para {destino} ...")

    with requests.get(url, stream=True, timeout=60, headers=headers) as r:
        r.raise_for_status()
        resumed = offset > 0 and r.status_code == 206
        if offset and not resumed:
            print("O servidor não aceitou a retomada; reiniciando o download.")
            offset = 0
        total = offset + int(r.headers.get("Content-Length", 0))
        baixado = offset
        mode = "ab" if resumed else "wb"
        with open(parcial, mode) as f:
            for pedaco in r.iter_content(chunk_size=1024 * 1024):
                if not pedaco:
                    continue
                f.write(pedaco)
                baixado += len(pedaco)
                if total:
                    print(
                        f"\r  {baixado / 1e6:.0f}/{total / 1e6:.0f} MB "
                        f"({baixado / total:.0%})",
                        end="",
                        flush=True,
                    )
    print()
    os.replace(parcial, destino)
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


def carregar_inicio_contests():
    """Baixa (sob demanda, não no import) o início de cada contest."""
    print("Obtendo datas dos contests...", flush=True)
    resp = requests.get(CONTESTS, timeout=60)
    resp.raise_for_status()
    contests = pd.DataFrame(resp.json())
    print(f"Datas de {len(contests):,} contests carregadas.", flush=True)
    return (contests[["id", "start_epoch_second"]]
            .rename(columns={"id": "contest_id",
                             "start_epoch_second": "contest_start_epoch"}))


def _prioridade_resultado(valor):
    """Prioridade para ordenar submissões úteis antes de aplicar caps."""
    if pd.isna(valor):
        return 99
    texto = str(valor).strip().upper()
    ordem = {"AC": 0, "WA": 1, "TLE": 2, "RE": 3, "CE": 4, "MLE": 5, "OLE": 6, "QLE": 7}
    return ordem.get(texto, 99)


def _aplicar_caps(df, max_por_problema=None, max_por_contest=None, seed=42):
    """Aplica deduplicação por usuário/problema e limita o número de linhas.

    Embaralha com seed fixa antes de ordenar (a ordenação é estável): dentro de cada nível de
    prioridade a escolha é aleatória e reprodutível, em vez de favorecer quem submeteu primeiro.
    """
    if df.empty:
        return df

    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)

    if "result" in df.columns:
        df["_resultado_ordem"] = df["result"].map(_prioridade_resultado)
    else:
        df["_resultado_ordem"] = 99

    if {"contest_id", "problem_id", "user_id"}.issubset(df.columns):
        df = df.sort_values(
            ["contest_id", "problem_id", "user_id", "_resultado_ordem"],
            ascending=[True, True, True, True],
            kind="mergesort",
        )
        df = df.drop_duplicates(subset=["contest_id", "problem_id", "user_id"], keep="first")

    if max_por_problema is not None and {"contest_id", "problem_id"}.issubset(df.columns):
        df = df.sort_values(
            ["contest_id", "problem_id", "_resultado_ordem"],
            ascending=[True, True, True],
            kind="mergesort",
        )
        df = df.groupby(["contest_id", "problem_id"], group_keys=False).head(max_por_problema)

    if max_por_contest is not None and "contest_id" in df.columns:
        df = df.sample(frac=1, random_state=seed)  # evita favorecer os primeiros problemas (a, b, ...)
        df = df.sort_values(
            ["contest_id", "_resultado_ordem"],
            ascending=[True, True],
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
    seed=42,
):
    if max_por_problema is not None and max_por_problema <= 0:
        raise ValueError("max_por_problema deve ser maior que zero.")
    if max_por_contest is not None and max_por_contest <= 0:
        raise ValueError("max_por_contest deve ser maior que zero.")

    if dataset_path is not None:
        if not os.path.exists(dataset_path):
            raise FileNotFoundError(
                f"Dataset não encontrado: {dataset_path}. "
                "Remova --csv para baixar o dataset automaticamente, "
                "ou informe o caminho de um arquivo local existente."
            )
        subs = dataset_path
    else:
        subs = garantir_dataset()

    saida_path = Path(saida)
    saida_path.parent.mkdir(parents=True, exist_ok=True)

    corte_epoch = pd.Timestamp(corte, tz=TZ).timestamp() if corte else None
    envio_de_epoch = para_epoch(envio_de) if envio_de else None
    envio_ate_epoch = para_epoch(envio_ate, fim=True) if envio_ate else None   # exclusivo

    if envio_de_epoch and envio_ate_epoch and envio_de_epoch >= envio_ate_epoch:
        raise ValueError("envio_de deve ser anterior a envio_ate.")

    tamanho_gib = Path(subs).stat().st_size / (1024 ** 3)
    print(
        f"Iniciando filtro de {subs} ({tamanho_gib:.2f} GiB), "
        "em blocos de 1.000.000 linhas...",
        flush=True,
    )
    inicio = carregar_inicio_contests()
    blocos = []
    inicio_leitura = time.monotonic()
    linhas_lidas = 0
    blocos_lidos = 0
    for bloco in pd.read_csv(subs, chunksize=1_000_000):   # pandas detecta o .gz pela extensão
        blocos_lidos += 1
        linhas_lidas += len(bloco)
        if blocos_lidos == 1 or blocos_lidos % 5 == 0:
            print(
                f"Filtro: bloco {blocos_lidos} recebido | "
                f"{linhas_lidas:,} linhas lidas | "
                f"{time.monotonic() - inicio_leitura:.0f}s",
                flush=True,
            )
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
        atomic_replace(saida_path, lambda path: pd.DataFrame().to_csv(path, index=False))
        print(
            f"Nenhuma submissão passou nos filtros ({saida} vazio). "
            f"{linhas_lidas:,} linhas lidas.",
            flush=True,
        )
        return saida

    final = pd.concat(blocos, ignore_index=True)
    if max_por_problema is not None or max_por_contest is not None:
        final = _aplicar_caps(final, max_por_problema=max_por_problema, max_por_contest=max_por_contest, seed=seed)

    atomic_replace(saida_path, lambda path: final.to_csv(path, index=False))
    print(
        f"Gerado: {saida} ({len(final):,} linhas de {linhas_lidas:,} lidas; "
        f"{time.monotonic() - inicio_leitura:.0f}s)",
        flush=True,
    )
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
    ap.add_argument("--seed", type=int, default=42, help="Seed da amostragem aleatória dos caps.")
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
        seed=args.seed,
    )
    return args.out


if __name__ == "__main__":
    main()