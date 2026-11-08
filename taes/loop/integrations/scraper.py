"""Scraping do enunciado e dos exemplos de um problema do AtCoder."""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from taes.core.models import Problem

from ...core.config import HEADERS


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


_SESSION = make_session()


def scrape_problem(problem_id: str) -> Problem:
    """Retorna {"id", "contest", "statement", "samples": [(entrada, saída_esperada), ...]}."""
    contest = problem_id.rsplit("_", 1)[0]
    url = f"https://atcoder.jp/contests/{contest}/tasks/{problem_id}?lang=en"
    r = _SESSION.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    root = soup.select_one("#task-statement")
    if root is None:
        raise ValueError(f"enunciado não encontrado em {url}")

    for ja in root.select(".lang-ja"):  # a página traz os dois idiomas no HTML
        ja.decompose()
    title_el = soup.select_one("title")
    title = title_el.get_text(strip=True) if title_el else ""

    # AtCoder pode renderizar os títulos dos exemplos vazios em algumas páginas;
    # quando isso acontece, usamos a ordem das partes da seção de I/O como fallback.
    ins: dict[int, str] = {}
    outs: dict[int, str] = {}
    for h3 in root.find_all("h3"):
        m = re.match(r"Sample (Input|Output)\s+(\d+)", h3.get_text(strip=True))
        pre = h3.find_next("pre")
        if not m or pre is None:
            continue
        (ins if m.group(1) == "Input" else outs)[int(m.group(2))] = pre.get_text().strip()

    if not ins and not outs:
        io_blocks = root.select(".io-style .part")
        for block in io_blocks:
            pre = block.select_one("pre")
            section = block.select_one("section")
            value = pre.get_text("\n", strip=True) if pre is not None else section.get_text("\n", strip=True) if section is not None else ""
            if not value:
                continue
            if not ins:
                ins[1] = value
            elif len(ins) == 1 and len(outs) == 0:
                outs[1] = value
            else:
                # continua emparelhando por ordem, quando houver mais de 2 blocos
                if len(outs) < len(ins):
                    outs[len(ins)] = value
                else:
                    ins[len(ins) + 1] = value

    samples = []
    if ins or outs:
        numbers = sorted(set(ins) | set(outs))
        samples = [(ins.get(n, "") + "\n", outs.get(n, "")) for n in numbers if n in ins and n in outs]

    statement = re.sub(r"\n{3,}", "\n\n", root.get_text("\n")).strip()
    return {"id": problem_id, "contest": contest, "title": title, "statement": statement, "samples": samples}
