import argparse
import csv
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from taes.core.config import HEADERS
from taes.core.files import atomic_replace
from taes.core.paths import DEFAULT_FILTERED_SUBMISSIONS

BASE_URL = "https://atcoder.jp"
SLEEP = 1.5
DEFAULT_WORKERS = 4
DEFAULT_OUTPUT_DIR = os.path.join("outputs", "02_download", "AtCoder")
DEFAULT_METADATA_FILENAME = "02_download_atcoder_submissions_metadata.csv"
DEFAULT_PROBLEM_LIST_FILENAME = "02_download_atcoder_submissions_problems.csv"
PROBLEM_LIST_COLUMNS = ["contest", "problem", "problem_id", "url", "submissions_count"]

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

_thread_state = threading.local()


def _session() -> requests.Session:
    current = getattr(_thread_state, "session", None)
    if current is None:
        current = requests.Session()
        current.headers.update(HEADERS)
        _thread_state.session = current
    return current


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
    r = _session().get(url, timeout=30)
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
    metadata = pd.read_csv(csv_path)
    if "codigo_submissao" not in metadata.columns:
        raise ValueError(f"Metadata inválida: coluna 'codigo_submissao' ausente em {csv_path}")
    return set(metadata["codigo_submissao"].dropna().astype(int))


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
    atomic_replace(
        csv_path,
        lambda path: old.to_csv(path, index=False, encoding="utf-8-sig"),
    )


def append_csv_row(csv_path: str, row: dict):
    migrate_csv_if_needed(csv_path)
    new_file = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def build_problem_url(contest_id: str, problem_id: str) -> str:
    return f"{BASE_URL}/contests/{contest_id}/tasks/{problem_id}"


def export_problem_list_csv(metadata_csv: str, out_csv: str = None) -> str:
    """Cria um CSV compacto para uso pelo loop de resolução."""
    metadata_path = Path(metadata_csv)
    out_path = Path(out_csv) if out_csv else metadata_path.with_name(DEFAULT_PROBLEM_LIST_FILENAME)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not metadata_path.exists():
        atomic_replace(
            out_path,
            lambda path: pd.DataFrame(columns=PROBLEM_LIST_COLUMNS).to_csv(
                path, index=False, encoding="utf-8-sig"
            ),
        )
        return str(out_path)

    df = pd.read_csv(metadata_path)
    rows = []
    seen = set()
    counts = {}

    for _, row in df.iterrows():
        problem_id = str(row.get("pagina_problema") or row.get("problem_id") or "").strip()
        if problem_id and "/tasks/" in problem_id:
            problem_id = problem_id.rsplit("/tasks/", 1)[1].strip()
        elif problem_id and problem_id.endswith(".py"):
            problem_id = problem_id.rsplit(".", 1)[0]
        if not problem_id:
            continue
        counts[problem_id] = counts.get(problem_id, 0) + 1

    for _, row in df.iterrows():
        problem_id = str(row.get("pagina_problema") or row.get("problem_id") or "").strip()
        if problem_id and "/tasks/" in problem_id:
            problem_id = problem_id.rsplit("/tasks/", 1)[1].strip()
        elif problem_id and problem_id.endswith(".py"):
            problem_id = problem_id.rsplit(".", 1)[0]

        contest = str(row.get("sigla_campeonato") or row.get("campeonato") or "").strip()
        if not contest and problem_id:
            contest = problem_id.rsplit("_", 1)[0] if "_" in problem_id else ""

        if not problem_id:
            continue

        url = str(row.get("pagina_problema") or "").strip()
        if not url and contest:
            url = build_problem_url(contest, problem_id)

        problem = str(row.get("nome_problema") or row.get("problem") or problem_id).strip()
        if not problem:
            problem = problem_id

        key = (contest, problem_id)
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "contest": contest,
            "problem": problem,
            "problem_id": problem_id,
            "url": url,
            "submissions_count": counts.get(problem_id, 0),
        })

    atomic_replace(
        out_path,
        lambda path: pd.DataFrame(rows, columns=PROBLEM_LIST_COLUMNS).to_csv(
            path, index=False, encoding="utf-8-sig"
        ),
    )
    return str(out_path)


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def download_submissions_from_df(df: pd.DataFrame,
                                 output_dir: str = DEFAULT_OUTPUT_DIR,
                                 only_ac: bool = True,
                                 metadata_csv: str = None,
                                 workers: int = DEFAULT_WORKERS,
                                 delay: float = SLEEP):
    """
    Estrutura gerada:
        <output_dir>/
            submissoes.csv
            <contest_id>/
                <problem_id>/
                    <sub_id>_<veredito>.<ext>
    """
    if workers < 1:
        raise ValueError("workers deve ser maior que zero.")
    if delay < 0:
        raise ValueError("delay não pode ser negativo.")

    os.makedirs(output_dir, exist_ok=True)
    metadata_csv = metadata_csv or os.path.join(output_dir, DEFAULT_METADATA_FILENAME)
    os.makedirs(os.path.dirname(metadata_csv) or ".", exist_ok=True)
    done_ids = load_done_ids(metadata_csv)

    baixadas = falhas = puladas = 0
    problemas_vistos = set()
    total = len(df)

    pending = []
    scheduled_ids = set(done_ids)
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

        if sub_id in scheduled_ids:
            print(f"{tag} já baixada, pulando.")
            puladas += 1
            continue

        ext = get_file_extension(language)
        problem_dir = os.path.join(output_dir, sanitize(contest_id), sanitize(problem_id))
        os.makedirs(problem_dir, exist_ok=True)
        filename = f"{sub_id}_{sanitize(verdict)}.{ext}"
        filepath = os.path.join(problem_dir, filename)

        pending.append({
            "pos": pos,
            "tag": tag,
            "sub_id": sub_id,
            "contest_id": contest_id,
            "problem_id": problem_id,
            "language": language,
            "verdict": verdict,
            "filepath": filepath,
        })
        scheduled_ids.add(sub_id)

    def fetch(item):
        print(f"{item['tag']} [{item['verdict']}] baixando...")
        data = get_submission_data(item["contest_id"], item["sub_id"])
        if delay:
            time.sleep(delay)
        return item, data

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch, item): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            try:
                item, data = future.result()
                source_code = data["code"].replace("\r\n", "\n").replace("\r", "\n")
                with open(item["filepath"], "w", encoding="utf-8", newline="") as f:
                    f.write(source_code)

                append_csv_row(metadata_csv, {
                    "codigo_submissao": item["sub_id"],
                    "campeonato": data["contest_name"],
                    "sigla_campeonato": item["contest_id"],
                    "tempo_execucao_ms": data["exec_time_ms"],
                    "memoria_kb": data["memory_kb"],
                    "linguagem": item["language"],
                    "pagina_problema": f"{BASE_URL}/contests/{item['contest_id']}/tasks/{item['problem_id']}",
                    "nome_problema": data["problem_name"] or item["problem_id"],
                    "veredito": item["verdict"],
                    "arquivo": os.path.relpath(item["filepath"], output_dir),
                })
                print(f" -> Salvo em {item['filepath']}")
                baixadas += 1
                problemas_vistos.add((item["contest_id"], item["problem_id"]))
            except Exception as e:
                falhas += 1
                print(f" -> Erro ao baixar {item['sub_id']}: {e}")

    print("\n--- Resumo ---")
    print(f"Total analisadas : {total}")
    print(f"Baixadas         : {baixadas}")
    print(f"Puladas          : {puladas}")
    print(f"Problemas únicos : {len(problemas_vistos)}")
    print(f"Falhas           : {falhas}")
    print(f"CSV de metadados : {metadata_csv}")
    problem_list_csv = export_problem_list_csv(metadata_csv)
    print(f"CSV de problemas : {problem_list_csv}")


def build_parser():
    parser = argparse.ArgumentParser(description="Baixa submissões do AtCoder.")
    parser.add_argument("--csv", default=str(DEFAULT_FILTERED_SUBMISSIONS),
                        help="CSV de entrada com as submissões (colunas: id, contest_id, problem_id, language, result)")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIR, help="Pasta de saída")
    parser.add_argument("--all", action="store_true", help="Baixar todas, não apenas AC")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Downloads simultâneos (padrão: {DEFAULT_WORKERS}).")
    parser.add_argument("--delay", type=float, default=SLEEP,
                        help=f"Intervalo por worker após cada request, em segundos (padrão: {SLEEP}).")
    parser.add_argument("--contest", default=None,
                        help="Baixar só um campeonato (ID ou parte do nome, ex.: 'abc300' ou 'Beginner Contest 300')")
    parser.add_argument("--list-contests", action="store_true",
                        help="Lista os campeonatos presentes no CSV e sai")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
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
        workers=args.workers,
        delay=args.delay,
    )
    return args.out


if __name__ == "__main__":
    main()