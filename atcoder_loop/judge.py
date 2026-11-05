"""Submissão de soluções para o AtCoder."""
from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from .config import HEADERS

log = logging.getLogger(__name__)

Submitter = Callable[[dict, str], dict]


def _read_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _pick_submit_language(options: list[str], code: str) -> str:
    """Escolhe a linguagem de forma determinística.

    ATCODER_LANGUAGE (substring do rótulo, ex.: "CPython 3.11") tem prioridade; por padrão
    usa CPython, para não misturar com PyPy (afeta a comparação de tempo/memória).
    """
    preferred = _read_env("ATCODER_LANGUAGE")
    if preferred:
        for label in options:
            if preferred.lower() in label.lower():
                return label
        raise ValueError(f"ATCODER_LANGUAGE='{preferred}' não casa com nenhuma opção: {options}")
    pythons = [label for label in options if "python" in label.lower()]
    for label in pythons:
        if "cpython" in label.lower():
            return label
    if pythons:
        return pythons[0]
    return options[0] if options else "Python (CPython 3.11.4)"


def _extract_readable_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _get_login_form_token(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    token = soup.select_one("input[name='csrf_token']")
    if token is not None:
        return token.get("value")
    token = soup.select_one("input[name='csrfToken']")
    if token is not None:
        return token.get("value")
    return None


def _set_cookie_string(session: requests.Session, raw_cookie: str) -> None:
    cookie_text = (raw_cookie or "").strip()
    if not cookie_text:
        return
    if os.path.exists(cookie_text):
        cookie_text = Path(cookie_text).read_text(encoding="utf-8", errors="ignore")

    if "=" not in cookie_text:
        session.cookies.set("REVEL_SESSION", cookie_text, domain="atcoder.jp")
        return

    # Aceita duas formas: "name=value; name2=value2" ou um valor bruto para REVEL_SESSION.
    # O formato bruto é comum quando o usuário copia apenas o valor do cookie no navegador.
    if cookie_text.count("=") == 1 and not any(ch in cookie_text for ch in ";, "):
        first_name, first_value = cookie_text.split("=", 1)
        if first_name.strip().lower() in {"revel_session", "session"}:
            session.cookies.set(first_name.strip(), first_value.strip(), domain="atcoder.jp")
            return
        session.cookies.set(first_name.strip(), first_value.strip(), domain="atcoder.jp")
        return

    for chunk in cookie_text.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            session.cookies.set(name, value, domain="atcoder.jp")


def _is_cloudflare_challenge(response: requests.Response | None) -> bool:
    """Só considera desafio quando a página realmente é o desafio; 429 (rate limit) não é captcha."""
    if response is None:
        return False
    html = (response.text or "").lower()
    if "verify you are human" in html or "cf-challenge" in html or "challenge-platform" in html:
        return True
    return response.status_code in {403, 503} and ("cloudflare" in html or "turnstile" in html)


def _copy_text_to_clipboard(text: str) -> bool:
    text = text or ""
    if not text:
        return False

    def _try_copy(cmd: list[str]) -> bool:
        try:
            completed = subprocess.run(cmd, input=text, text=True, check=False, capture_output=True)
            return completed.returncode == 0
        except OSError:
            return False

    try:
        system_name = platform.system().lower()

        if system_name == "windows":
            commands = (
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                ["clip"],
            )
            for cmd in commands:
                if _try_copy(cmd):
                    return True

        if system_name == "darwin":
            if _try_copy(["pbcopy"]):
                return True

        for cmd in (
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            if _try_copy(cmd):
                return True

        try:
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            return True
        except Exception:
            return False
    except Exception:
        return False

    return False


def _wait_for_manual_submission_confirmation(code: str = "") -> None:
    if code:
        print("\nCódigo disponível na área de transferência (Ctrl+V para colar no AtCoder).")
        print("Opções: [1] Copiar novamente o código para a área de transferência | [2] Continuar sem copiar")
        choice = input("Digite 1 para copiar novamente ou 2 para continuar: ").strip()
        if choice == "1":
            _copy_text_to_clipboard(code)
            print("Código copiado novamente para a área de transferência.")
        elif choice == "2":
            print("Continuando sem copiar; irei consultar a submissão assim que ela aparecer no AtCoder.")
            return

    print("Abra a página de submissão do problema, cole o código, envie a solução e confirme a submissão.")
    input("Quando a submissão estiver concluída, pressione Enter para continuar e recuperar o resultado...\n")


def _handle_manual_captcha(
    session: requests.Session,
    contest: str,
    problem_id: str,
    task_url: str,
    code: str = "",
    language_id: str | None = None,
    session_cookie: str | None = None,
    after_id: int = 0,
) -> dict:
    browser_task_url = task_url if task_url.startswith("http") else f"https://atcoder.jp{task_url}"
    login_url = "https://atcoder.jp/login"
    continue_url = quote(browser_task_url, safe="")
    login_continue_url = f"{login_url}?continue={continue_url}"

    print("\nValidação manual do AtCoder detectada.")
    print("Abrindo a página da tarefa no navegador padrão do sistema e copiando o código para a área de transferência.")
    print(f"Login: {login_continue_url}")
    print(f"Tarefa: {browser_task_url}")

    if code:
        _copy_text_to_clipboard(code)

    try:
        webbrowser.open(browser_task_url)
    except Exception:
        try:
            webbrowser.open(login_continue_url)
        except Exception:
            pass

    _wait_for_manual_submission_confirmation(code)
    return _handle_manual_captcha_fallback(session, contest, after_id)


def _handle_manual_captcha_fallback(session: requests.Session, contest: str, after_id: int = 0) -> dict:
    status, time_ms, memory_kb = _wait_for_verdict(session, contest, after_id)
    return {
        "verdict": status,
        "time_ms": time_ms,
        "memory_kb": memory_kb,
        "reason": "Submissão manual concluída após validação do navegador do usuário.",
        "feedback": _build_feedback(status, time_ms, memory_kb),
    }


def _is_authenticated(session: requests.Session) -> bool:
    try:
        page = session.get("https://atcoder.jp/", timeout=30)
        page.raise_for_status()
        text = _extract_readable_text(page.text).lower()
        return "logout" in text or "sign out" in text or "my submissions" in text
    except Exception:
        return False


def _ensure_authenticated(session: requests.Session, session_cookie: str | None = None) -> None:
    if _is_authenticated(session):
        return

    cookie_value = session_cookie or _read_env("ATCODER_SESSION_COOKIE", "ATCODER_COOKIES")
    if not cookie_value:
        raise ValueError(
            "Cookie de sessão do AtCoder ausente. Defina ATCODER_SESSION_COOKIE/ATCODER_COOKIES "
            "com o valor do cookie REVEL_SESSION ou o bloco completo de cookies autenticados."
        )

    _set_cookie_string(session, cookie_value)
    if not _is_authenticated(session):
        raise ValueError(
            "Cookie de sessão do AtCoder inválido ou expirado. Gere uma nova sessão autenticada e exporte "
            "ATCODER_SESSION_COOKIE/ATCODER_COOKIES."
        )


VERDICT_ALIASES: dict[str, tuple[str, ...]] = {
    "AC": ("AC", "Accepted"),
    "WA": ("WA", "Wrong Answer"),
    "TLE": ("TLE", "Time Limit Exceeded"),
    "RE": ("RE", "Runtime Error"),
    "CE": ("CE", "Compilation Error"),
    "MLE": ("MLE", "Memory Limit Exceeded"),
    "OLE": ("OLE", "Output Limit Exceeded"),
    "PE": ("PE", "Presentation Error"),
    "QLE": ("QLE", "QLE"),
    "SE": ("SE", "System Error"),
    "IE": ("IE", "Judge Error"),
    "WJ": ("WJ", "Judging"),
}


def _matches_verdict_alias(text: str, alias: str) -> bool:
    if not text or not alias:
        return False
    lower = text.lower()
    candidate = alias.lower()
    if len(candidate) <= 3:
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(candidate)}(?![A-Za-z0-9])", lower))
    return bool(re.search(rf"(?<![A-Za-z]){re.escape(candidate)}(?![A-Za-z])", lower))


def _extract_verdict(text: str) -> str | None:
    if not text:
        return None

    matches: list[str] = []
    for status, aliases in VERDICT_ALIASES.items():
        if any(_matches_verdict_alias(text, alias) for alias in aliases):
            matches.append(status)

    if not matches:
        return None

    return matches[-1]


def _find_submit_form(soup: BeautifulSoup) -> tuple[str, dict[str, str]]:
    for form in soup.find_all("form"):
        form_names = {input_.get("name") for input_ in form.find_all(["input", "textarea", "select"]) if input_.get("name")}
        if not form_names:
            continue
        matches = {
            "source_code",
            "sourceCode",
            "taskScreenName",
            "task_screen_name",
            "data.TaskScreenName",
            "language_id",
            "languageId",
            "data.LanguageId",
        }
        if matches & form_names:
            action = form.get("action") or "/contests/submit"
            payload = {}
            for input_ in form.find_all(["input", "textarea", "select"]):
                name = input_.get("name")
                if not name:
                    continue
                if input_.name == "select":
                    selected = input_.find("option", selected=True) or input_.find("option")
                    payload[name] = selected.get("value", "") if selected is not None else ""
                    continue
                if input_.get("type") in {"submit", "button"}:
                    continue
                payload[name] = input_.get("value", "")
            return action, payload
    raise ValueError("Formulário de submissão do AtCoder não encontrado no enunciado.")


def _coerce_int(value, unit: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None

    match = re.fullmatch(r"\s*([0-9][0-9,]*(?:\.\d+)?)\s*(ms|kb|kib|mb|mib|m|k)\s*", text, flags=re.IGNORECASE)
    if not match:
        return None

    number = float(match.group(1).replace(",", ""))
    unit_text = match.group(2).lower()
    if unit == "ms":
        if unit_text == "ms":
            return int(number)
        return None
    if unit == "kb":
        if unit_text in {"kb", "k", "kib"}:
            return int(number)
        if unit_text in {"mb", "m", "mib"}:
            return int(number * 1024)
        return None
    return None


_SUBMISSION_ID_RE = re.compile(r"/submissions/(\d+)(?:[?#]|$)")
_FINAL_VERDICTS = {"AC", "WA", "TLE", "RE", "CE", "MLE", "OLE", "PE", "QLE", "SE", "IE"}
_VERDICT_HINTS = {
    "WA": "Wrong Answer: the program ran but its output differs from the expected output on some hidden test.",
    "TLE": "Time Limit Exceeded: the program is too slow on some hidden test; use a faster algorithm or faster I/O.",
    "RE": "Runtime Error: the program crashed (exception, bad input parsing, recursion limit, ...) on some hidden test.",
    "CE": "Compilation Error: the code has a syntax error.",
    "MLE": "Memory Limit Exceeded: the program uses too much memory on some hidden test.",
    "OLE": "Output Limit Exceeded: the program prints too much output.",
    "WJ": "The judge did not finish in time (infrastructure issue, not necessarily a bug in the code).",
}


def _my_submission_rows(session: requests.Session, contest: str) -> list[dict]:
    """Linhas de /submissions/me (mais recente primeiro): id, veredito bruto, tempo e memória."""
    url = f"https://atcoder.jp/contests/{contest}/submissions/me"
    response = session.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    for tr in soup.select("table tbody tr"):
        sub_id = None
        for a in tr.find_all("a", href=True):
            m = _SUBMISSION_ID_RE.search(a["href"])
            if m:
                sub_id = int(m.group(1))
        if sub_id is None:
            continue
        label = tr.select_one("td span.label") or tr.select_one("td[data-id] span")
        status_text = label.get_text(" ", strip=True) if label is not None else ""
        time_ms = memory_kb = None
        for cell in (c.get_text(" ", strip=True) for c in tr.find_all("td")):
            parsed_time = _coerce_int(cell, "ms")
            if parsed_time is not None:
                time_ms = parsed_time
            parsed_memory = _coerce_int(cell, "kb")
            if parsed_memory is not None:
                memory_kb = parsed_memory
        rows.append({"id": sub_id, "status_text": status_text, "time_ms": time_ms, "memory_kb": memory_kb})
    rows.sort(key=lambda r: r["id"], reverse=True)
    return rows


def _latest_submission_id(session: requests.Session, contest: str) -> int:
    rows = _my_submission_rows(session, contest)
    return rows[0]["id"] if rows else 0


def _submission_status(session: requests.Session, contest: str, after_id: int = 0) -> tuple[str, int | None, int | None]:
    """Veredito da submissão mais recente com id > after_id.

    Só lê a célula de status dessa linha (nunca cai para submissões antigas). Se a submissão
    ainda não apareceu, ou o status é "WJ"/progresso ("3/30"), devolve "WJ".
    """
    for row in _my_submission_rows(session, contest):
        if row["id"] <= after_id:
            break
        verdict = _extract_verdict(row["status_text"])
        if verdict is None or verdict == "WJ":
            return "WJ", None, None
        return verdict, row["time_ms"], row["memory_kb"]
    return "WJ", None, None


def _wait_for_verdict(session: requests.Session, contest: str, after_id: int,
                      attempts: int = 45, interval: float = 2.0) -> tuple[str, int | None, int | None]:
    status, time_ms, memory_kb = "WJ", None, None
    for _ in range(attempts):
        try:
            status, time_ms, memory_kb = _submission_status(session, contest, after_id)
        except requests.RequestException:
            log.debug("[judge] falha ao consultar status", exc_info=True)
            status = "WJ"
        if status != "WJ":
            break
        time.sleep(interval)
    return status, time_ms, memory_kb


def _build_feedback(status: str, time_ms: int | None, memory_kb: int | None) -> str:
    parts = [f"AtCoder verdict: {status}."]
    parts.append(_VERDICT_HINTS.get(status, ""))
    if time_ms is not None:
        parts.append(f"Execution time: {time_ms} ms.")
    if memory_kb is not None:
        parts.append(f"Memory: {memory_kb} KB.")
    parts.append("AtCoder does not reveal the failing test case.")
    return " ".join(p for p in parts if p)


def submit_atcoder(problem: dict, code: str, session_cookie: str | None = None) -> dict:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

    contest = problem.get("contest") or str(problem.get("problem_id", "")).rsplit("_", 1)[0]
    problem_id = problem.get("id") or problem.get("problem_id") or ""
    if not contest or not problem_id:
        raise ValueError("problem precisa conter 'contest' e 'id' (ou 'problem_id').")

    session = requests.Session()
    session.headers.update(HEADERS)
    _ensure_authenticated(session, session_cookie)

    task_url = f"https://atcoder.jp/contests/{contest}/tasks/{problem_id}?lang=en"
    task_page = session.get(task_url, timeout=30)
    task_page.raise_for_status()
    soup = BeautifulSoup(task_page.text, "html.parser")
    action_url = f"https://atcoder.jp/contests/{contest}/submit"
    language_id = None
    payload: dict[str, str] = {"source_code": code}

    submit_form_action, form_payload = _find_submit_form(soup)
    action_url = submit_form_action if submit_form_action.startswith("http") else f"https://atcoder.jp/{submit_form_action}"
    if submit_form_action.startswith("/"):
        action_url = f"https://atcoder.jp{submit_form_action}"

    payload.update(form_payload)
    payload["source_code"] = code
    payload["sourceCode"] = code
    payload["taskScreenName"] = problem_id
    payload["task_screen_name"] = problem_id
    payload["data.TaskScreenName"] = problem_id
    payload["contest_id"] = contest

    language_keys = ("data.LanguageId", "language_id", "languageId", "language")
    select = None
    for key in language_keys:
        if key in payload:
            maybe_select = soup.select_one(f"select[name='{key}']")
            if maybe_select is not None:
                select = maybe_select
                break
        maybe_select = soup.select_one(f"select[name=\"{key}\"]")
        if maybe_select is not None:
            select = maybe_select
            break
    if select is not None:
        options = [option.get_text(" ", strip=True) for option in select.find_all("option")]
        selected = _pick_submit_language([opt for opt in options if opt], code)
        chosen = None
        for option in select.find_all("option"):
            label = option.get_text(" ", strip=True)
            if label == selected:
                chosen = option.get("value")
                break
        if chosen is not None:
            language_id = chosen
            for key in language_keys:
                payload[key] = chosen
            payload["languageId"] = chosen
            payload["language_id"] = chosen
            payload["data.LanguageId"] = chosen

    if language_id is None:
        for candidate in language_keys:
            if candidate in payload and payload[candidate]:
                language_id = payload[candidate]
                break
        if language_id is None:
            raise ValueError("Não foi possível detectar a linguagem de submissão no AtCoder.")

    payload["csrf_token"] = _get_login_form_token(task_page.text) or payload.get("csrf_token") or ""
    if not payload["csrf_token"]:
        token_page = session.get(action_url, timeout=30)
        token_page.raise_for_status()
        payload["csrf_token"] = _get_login_form_token(token_page.text) or ""

    if not payload.get("data.TaskScreenName"):
        payload["data.TaskScreenName"] = problem_id
    if not payload.get("data.LanguageId") and language_id:
        payload["data.LanguageId"] = language_id

    baseline_id = _latest_submission_id(session, contest)
    submit_response = session.post(action_url, data=payload, timeout=60)
    if _is_cloudflare_challenge(submit_response):
        fallback = _handle_manual_captcha(session, contest, problem_id, task_url, code, language_id, session_cookie,
                                          after_id=baseline_id)
        return {
            "verdict": fallback["verdict"],
            "time_ms": fallback["time_ms"],
            "memory_kb": fallback["memory_kb"],
            "reason": fallback["reason"],
            "feedback": fallback["feedback"],
        }

    submit_response.raise_for_status()
    status, time_ms, memory_kb = _wait_for_verdict(session, contest, baseline_id)
    feedback = _build_feedback(status, time_ms, memory_kb)
    return {
        "verdict": status,
        "time_ms": time_ms,
        "memory_kb": memory_kb,
        "reason": "Accepted" if status == "AC" else feedback,
        "feedback": feedback,
    }
