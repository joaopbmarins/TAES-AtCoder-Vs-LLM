import os
import pandas as pd
import requests

SUBS_URL = "https://s3-ap-northeast-1.amazonaws.com/kenkoooo/submissions.csv.gz"
SUBS_CANDIDATOS = ["submissions.csv", "submissions.csv.gz"]   # ordem de preferência
CONTESTS = "https://kenkoooo.com/atcoder/resources/contests.json"
TZ = "America/Sao_Paulo"


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


def processar(
    contests_lista=None,      # ex.: ["abc300", "abc301", "arc160"]
    prefixos_contest=None,    # ex.: ["abc", "arc"]  (todos os ABC e ARC)
    linguagens=None,          # ex.: ["C++", "Python"] (começa com...)
    linguagens_exatas=None,   # ex.: ["C++ 20 (gcc 12.2)"]
    resultados=["AC"],        # padrão: só aprovadas; use None para manter todos
    corte=None,               # "YYYY-MM-DD" (início do contest)
    envio_de=None,            # início da janela de envio: "YYYY-MM-DD" ou "YYYY-MM-DD HH:MM"
    envio_ate=None,           # fim da janela de envio (inclusivo se for só data)
    saida="submissoes_filtradas.csv",
):
    subs = garantir_dataset()            # .csv ou .csv.gz; baixa se faltar

    # evita sobrar arquivo antigo de uma execução anterior
    if os.path.exists(saida):
        os.remove(saida)

    corte_epoch = pd.Timestamp(corte, tz=TZ).timestamp() if corte else None
    envio_de_epoch = para_epoch(envio_de) if envio_de else None
    envio_ate_epoch = para_epoch(envio_ate, fim=True) if envio_ate else None   # exclusivo

    if envio_de_epoch and envio_ate_epoch and envio_de_epoch >= envio_ate_epoch:
        raise ValueError("envio_de deve ser anterior a envio_ate.")

    primeiro = True

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

        bloco.to_csv(saida, mode="w" if primeiro else "a",
                     header=primeiro, index=False)
        primeiro = False

    if primeiro:
        print(f"Nenhuma submissão passou nos filtros ({saida} não foi criado).")
    else:
        print(f"Gerado: {saida}")


if __name__ == "__main__":
    # exemplo: submissões enviadas entre 01/03/2025 e 31/03/2025 (março inteiro)
    processar(
        prefixos_contest=["abc"],
        linguagens=["Python", "PyPy"],
        envio_de="2025-03-01",
        envio_ate="2025-03-31",
        saida="abc_py_marco_2025.csv",
    )

    # exemplo: janela com horário
    # processar(
    #     contests_lista=["abc300", "abc301", "abc302"],
    #     envio_de="2026-03-04 21:00",
    #     envio_ate="2026-03-05 00:00",
    #     saida="abc_janela_horario.csv",
    # )

    # exemplo: só limite inferior (tudo enviado a partir de uma data)
    # processar(prefixos_contest=["abc"], envio_de="2026-06-01", saida="abc_desde_junho.csv")