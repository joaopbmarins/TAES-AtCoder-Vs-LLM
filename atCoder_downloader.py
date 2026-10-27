import os
import re
import csv
import json
import time
import argparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://atcoder.jp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
SLEEP = 1.5

# Ordem importa: "c++" e "c#" devem ser testados antes de "c ".
EXTENSION_MAP = {
    "rust": "rs",
    "python": "py",
    "pypy": "py",
    "c++": "cpp",
    "c#": "cs",
    "java": "java",
    "kotlin": "kt",
    "go ": "go",
    "c ": "c",
}

CSV_COLUMNS = [
    "codigo_submissao",
    "campeonato",
    "sigla_campeonato",
    "tempo_execucao_ms",
    "memoria_kb",
    "linguagem",
    "pagina_problema",
    "nome_problema",
    # extras úteis
    "veredito",
    "arquivo",
]

session = requests.Session()
session.headers.update(HEADERS)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def get_file_extension(language_str: str) -> str:
    lang_lower = str(language_str).lower()
    for key, ext in EXTENSION_MAP.items():
        if key in lang_lower:
            return ext
    return "txt"


def sanitize(name: str) -> str:
    """Remove caracteres inválidos para nome de pasta/arquivo."""
    return re.sub(r'[<>:"/\\|?*]', "_", str(name)).strip()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def get_page(url: str) -> BeautifulSoup:
    r = session.get(url, timeout=30)
    if r.status_code != 200:
        raise Exception(f"Falha ao carregar {url} (status {r.status_code})")
    return BeautifulSoup(r.text, "html.parser")


def first_int(text: str):
    m = re.search(r"\d+", str(text).replace(",", ""))
    return int(m.group()) if m else None


# --------------------------------------------------------------------------
# Scraping
# --------------------------------------------------------------------------
def get_submission_data(contest_id: str, submission_id: int) -> dict:
    """Baixa a página da submissão e extrai código + metadados."""
    soup = get_page(f"{BASE_URL}/contests/{contest_id}/submissions/{submission_id}?lang=en")

    code_element = soup.find("pre", id="submission-code")
    if not code_element:
        raise ValueError("Não encontrei o elemento do código-fonte.")

    title_el = soup.select_one("a.contest-title")
    contest_name = title_el.get_text(strip=True) if title_el else contest_id

    info = {}
    for tr in soup.select("table tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            info[normalize(th.get_text())] = td

    task_td = info.get("task")
    problem_name = task_td.get_text(" ", strip=True) if task_td else None

    exec_time = memory = None
    for key, td in info.items():
        if "time" in key:
            exec_time = first_int(td.get_text())
        elif "memory" in key:
            memory = first_int(td.get_text())

    return {
        "code": code_element.get_text().lstrip("\n"),
        "contest_name": contest_name,
        "problem_name": problem_name,
        "exec_time_ms": exec_time,
        "memory_kb": memory,
    }


# --------------------------------------------------------------------------
# Resolução de campeonato por nome
# --------------------------------------------------------------------------
def load_name_cache(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_name_cache(path: str, cache: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_contest_name(contest_id: str, cache: dict, cache_path: str) -> str:
    if contest_id in cache:
        return cache[contest_id]
    soup = get_page(f"{BASE_URL}/contests/{contest_id}?lang=en")
    el = soup.select_one("a.contest-title")
    name = el.get_text(strip=True) if el else contest_id
    cache[contest_id] = name
    save_name_cache(cache_path, cache)
    time.sleep(SLEEP)
    return name


def filter_by_contest(df: pd.DataFrame, query: str, cache_path: str) -> pd.DataFrame:
    """Filtra por ID ou por nome do campeonato (busca parcial, sem diferenciar maiúsculas)."""
    q = normalize(query)
    ids = df["contest_id"].astype(str).unique()

    # 1) Tenta casar com o ID (ex.: "abc300") — não precisa de rede
    matched = [c for c in ids if q in normalize(c)]

    # 2) Se não achou, resolve os nomes (com cache) e compara
    if not matched:
        print(f"Nenhum ID casa com '{query}'. Buscando nomes dos campeonatos...")
        cache = load_name_cache(cache_path)
        for c in ids:
            if q in normalize(get_contest_name(c, cache, cache_path)):
                matched.append(c)

    if not matched:
        print(f"Nenhum campeonato encontrado para '{query}'.")
        return df.iloc[0:0]

    print(f"Campeonatos selecionados: {', '.join(matched)}")
    return df[df["contest_id"].astype(str).isin(matched)]


def list_contests(df: pd.DataFrame, cache_path: str):
    cache = load_name_cache(cache_path)
    counts = df["contest_id"].astype(str).value_counts().sort_index()
    print(f"{'contest_id':<20} {'subs':>5}  nome")
    for cid, n in counts.items():
        print(f"{cid:<20} {n:>5}  {cache.get(cid, '(nome ainda não resolvido)')}")


# --------------------------------------------------------------------------
# CSV de metadados
# --------------------------------------------------------------------------
def load_done_ids(csv_path: str) -> set:
    if not os.path.exists(csv_path):
        return set()
    try:
        return set(pd.read_csv(csv_path)["codigo_submissao"].astype(int))
    except Exception:
        return set()


def migrate_csv_if_needed(csv_path: str):
    """Se o CSV existente tem cabeçalho antigo, reescreve com as colunas novas."""
    if not os.path.exists(csv_path):
        return
    old = pd.read_csv(csv_path)
    if list(old.columns) == CSV_COLUMNS:
        return
    if "sigla_campeonato" not in old.columns and "arquivo" in old.columns:
        # a sigla é a primeira pasta do caminho do arquivo
        old["sigla_campeonato"] = old["arquivo"].astype(str).str.split(r"[\\/]").str[0]
    old = old.reindex(columns=CSV_COLUMNS)
    old.to_csv(csv_path, index=False, encoding="utf-8-sig")


def append_csv_row(csv_path: str, row: dict):
    migrate_csv_if_needed(csv_path)
    new_file = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def download_submissions_from_df(df: pd.DataFrame,
                                 output_dir: str = "atcoder_submissions",
                                 only_ac: bool = True,
                                 metadata_csv: str = None):
    """
    Estrutura gerada:
        <output_dir>/
            submissoes.csv
            <contest_id>/
                <problem_id>/
                    <sub_id>_<veredito>.<ext>
    """
    os.makedirs(output_dir, exist_ok=True)
    metadata_csv = metadata_csv or os.path.join(output_dir, "submissoes.csv")
    done_ids = load_done_ids(metadata_csv)

    baixadas = falhas = puladas = 0
    problemas_vistos = set()
    total = len(df)

    for pos, (_, row) in enumerate(df.iterrows(), start=1):
        sub_id = int(row["id"])
        contest_id = str(row["contest_id"])
        problem_id = str(row["problem_id"])
        language = str(row["language"])
        verdict = str(row.get("result", "UNKNOWN"))
        tag = f"[{pos}/{total}] {sub_id} ({contest_id}/{problem_id})"

        if only_ac and verdict != "AC":
            print(f"{tag} não é AC ({verdict}), pulando.")
            puladas += 1
            continue

        if sub_id in done_ids:
            print(f"{tag} já baixada, pulando.")
            puladas += 1
            continue

        ext = get_file_extension(language)
        problem_dir = os.path.join(output_dir, sanitize(contest_id), sanitize(problem_id))
        os.makedirs(problem_dir, exist_ok=True)
        filename = f"{sub_id}_{sanitize(verdict)}.{ext}"
        filepath = os.path.join(problem_dir, filename)

        print(f"{tag} [{verdict}] baixando...")

        try:
            data = get_submission_data(contest_id, sub_id)
            source_code = data["code"].replace("\r\n", "\n").replace("\r", "\n")

            with open(filepath, "w", encoding="utf-8", newline="") as f:
                f.write(source_code)

            append_csv_row(metadata_csv, {
                "codigo_submissao": sub_id,
                "campeonato": data["contest_name"],
                "sigla_campeonato": contest_id,
                "tempo_execucao_ms": data["exec_time_ms"],
                "memoria_kb": data["memory_kb"],
                "linguagem": language,
                "pagina_problema": f"{BASE_URL}/contests/{contest_id}/tasks/{problem_id}",
                "nome_problema": data["problem_name"] or problem_id,
                "veredito": verdict,
                "arquivo": os.path.relpath(filepath, output_dir),
            })

            print(f" -> Salvo em {filepath}")
            baixadas += 1
            problemas_vistos.add((contest_id, problem_id))
            time.sleep(SLEEP)

        except Exception as e:
            falhas += 1
            print(f" -> Erro ao baixar {sub_id}: {e}")

    print("\n--- Resumo ---")
    print(f"Total analisadas : {total}")
    print(f"Baixadas         : {baixadas}")
    print(f"Puladas          : {puladas}")
    print(f"Problemas únicos : {len(problemas_vistos)}")
    print(f"Falhas           : {falhas}")
    print(f"CSV de metadados : {metadata_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baixa submissões do AtCoder.")
    parser.add_argument("--csv", default="submissoes_filtradas.csv",
                        help="CSV de entrada com as submissões (colunas: id, contest_id, problem_id, language, result)")
    parser.add_argument("--out", default="atcoder_submissions", help="Pasta de saída")
    parser.add_argument("--all", action="store_true", help="Baixar todas, não apenas AC")
    parser.add_argument("--contest", default=None,
                        help="Baixar só um campeonato (ID ou parte do nome, ex.: 'abc300' ou 'Beginner Contest 300')")
    parser.add_argument("--list-contests", action="store_true",
                        help="Lista os campeonatos presentes no CSV e sai")
    args = parser.parse_args()

    df_submissions = pd.read_csv(args.csv)
    os.makedirs(args.out, exist_ok=True)
    names_cache = os.path.join(args.out, "contest_names.json")

    if args.list_contests:
        list_contests(df_submissions, names_cache)
        raise SystemExit(0)

    if args.contest:
        df_submissions = filter_by_contest(df_submissions, args.contest, names_cache)

    download_submissions_from_df(
        df_submissions,
        output_dir=args.out,
        only_ac=not args.all,
    )