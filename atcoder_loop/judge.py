"""Submissão de soluções para o AtCoder."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Callable

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from .config import HEADERS

Submitter = Callable[[dict, str], dict]


def _read_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _pick_submit_language(options: list[str], code: str) -> str:
    lowered = code.lower()
    if any(token in lowered for token in ("import ", "def ", "print(", "input(", "from ")):
        for label in options:
            if "python" in label.lower():
                return label
    if any(token in lowered for token in ("#include", "std::", "using namespace", "cout", "cin")):
        for label in options:
            if "c++" in label.lower() or "cpp" in label.lower() or "gcc" in label.lower():
                return label
    return options[0] if options else "Python (CPython 3.11.4)"


def _extract_readable_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _extract_submission_reason(html: str) -> str | None:
    if not html:
        return None
    text = _extract_readable_text(html)
    for marker in (
        "Wrong Answer",
        "Runtime Error",
        "Time Limit Exceeded",
        "Memory Limit Exceeded",
        "Compilation Error",
        "Output Limit Exceeded",
        "Judge Error",
        "syntax error",
        "HTTP 500",
        "login",
        "csrf",
        "Not Found",
        "forbidden",
        "invalid",
        "session",
    ):
        if marker.lower() in text.lower():
            return text
    if len(text) > 500:
        return text[:500]
    return text or None


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
        session.cookies.set("REVEL_SESSION", cookie_text.split("=", 1)[1].strip(), domain="atcoder.jp")
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


def _has_turnstile_challenge(html: str) -> bool:
    text = (html or "").lower()
    return "cf-turnstile" in text or "challenges.cloudflare.com/turnstile" in text or "turnstile" in text


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


def _extract_verdict(text: str) -> str | None:
    if not text:
        return None
    for status in ("AC", "WA", "TLE", "RE", "CE", "MLE", "OLE", "PE", "QLE", "SE", "IE", "WJ"):
        if status in text.upper():
            return status
    return None


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


def _extract_metrics_from_html_fragment(fragment: str) -> tuple[str | None, int | None, int | None]:
    if not fragment:
        return None, None, None
    text = _extract_readable_text(fragment)
    status = _extract_verdict(text)
    if status is None:
        lower = text.lower()
        for marker in ("accepted", "wrong answer", "time limit exceeded", "memory limit exceeded", "runtime error", "compilation error"):
            if marker in lower:
                status = marker.title()
                break

    time_ms = None
    match = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*ms\b", text, flags=re.IGNORECASE)
    if match:
        time_ms = int(float(match.group("value")))

    memory_kb = None
    match = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*(?:(?P<unit>KB|KIB|MB|MIB))\b", text, flags=re.IGNORECASE)
    if match:
        value = float(match.group("value"))
        unit = (match.group("unit") or "KB").upper()
        if unit in {"MB", "MIB"}:
            value *= 1024
        memory_kb = int(value)

    return status, time_ms, memory_kb


def _extract_submission_metrics_from_payload(payload: object) -> tuple[str | None, int | None, int | None]:
    if isinstance(payload, dict):
        items = payload.get("Result") if "Result" in payload else payload
        if isinstance(items, dict):
            for value in items.values():
                if isinstance(value, dict):
                    status = _extract_verdict(str(value.get("Status") or value.get("status") or value.get("Verdict") or ""))
                    if status is None:
                        status = _extract_verdict(str(value.get("result") or value.get("name") or ""))
                    html = value.get("Html") or value.get("html")
                    if html:
                        html_status, time_ms, memory_kb = _extract_metrics_from_html_fragment(str(html))
                        if html_status is not None or time_ms is not None or memory_kb is not None:
                            return html_status or status, time_ms, memory_kb
                    time_ms = value.get("ExecutionTime") or value.get("Time") or value.get("time")
                    memory_kb = value.get("Memory") or value.get("MemoryUsage") or value.get("memory")
                    if time_ms is None:
                        for key in ("ExecutionTime", "Time", "time", "elapsed_ms"):
                            if key in value and isinstance(value[key], (int, float, str)):
                                time_ms = value[key]
                                break
                    if memory_kb is None:
                        for key in ("Memory", "MemoryUsage", "memory", "memory_kb"):
                            if key in value and isinstance(value[key], (int, float, str)):
                                memory_kb = value[key]
                                break
                    if status is not None or time_ms is not None or memory_kb is not None:
                        return status, _coerce_int(time_ms, "ms"), _coerce_int(memory_kb, "kb")
                elif isinstance(value, str):
                    status, time_ms, memory_kb = _extract_metrics_from_html_fragment(value)
                    if status is not None or time_ms is not None or memory_kb is not None:
                        return status, time_ms, memory_kb
        elif isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    status, time_ms, memory_kb = _extract_submission_metrics_from_payload(item)
                    if status is not None or time_ms is not None or memory_kb is not None:
                        return status, time_ms, memory_kb
    return None, None, None


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
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ms|kb|KB|MB|m|k)?", text, flags=re.IGNORECASE)
    if match:
        number = float(match.group(1))
        unit_text = (match.group(2) or "").lower()
        if unit == "ms":
            return int(number)
        if unit == "kb":
            if unit_text in {"mb", "m"}:
                return int(number * 1024)
            return int(number)
    if text.isdigit():
        return int(text)
    return None


def _submission_status(session: requests.Session, contest: str) -> tuple[str, int | None, int | None]:
    json_url = f"https://atcoder.jp/contests/{contest}/submissions/me/status/json"
    try:
        response = session.get(json_url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        status, time_ms, memory_kb = _extract_submission_metrics_from_payload(payload)
        if status is not None:
            return status, time_ms, memory_kb
    except Exception:
        pass

    url = f"https://atcoder.jp/contests/{contest}/submissions/me"
    response = session.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = list(soup.select("tr"))
    for row in reversed(rows):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if not cells:
            continue
        status = None
        for cell in cells:
            code = _extract_verdict(cell)
            if code:
                status = code
                break
        if status is None:
            continue
        time_ms = None
        memory_kb = None
        for cell in cells:
            time_ms = time_ms or _coerce_int(cell, "ms")
            memory_kb = memory_kb or _coerce_int(cell, "kb")
            if cell.endswith("ms") and cell[:-2].strip().isdigit():
                time_ms = int(cell[:-2].strip())
            if cell.endswith("KB") and cell[:-2].strip().isdigit():
                memory_kb = int(cell[:-2].strip())
        return status, time_ms, memory_kb
    match = _extract_verdict(response.text)
    return match or "WJ", None, None


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

    submit_response = session.post(action_url, data=payload, timeout=60)
    submit_response.raise_for_status()
    feedback_text = _extract_submission_reason(submit_response.text) or submit_response.text[:1000]

    status = "WJ"
    time_ms = None
    memory_kb = None
    for _ in range(12):
        status, time_ms, memory_kb = _submission_status(session, contest)
        if status not in {"WJ", "Judging"}:
            break
        time.sleep(2)

    if status == "WJ":
        status = _extract_verdict(submit_response.text) or status

    reason = feedback_text if status != "AC" else "Accepted"
    if status in {"AC", "WA", "TLE", "RE", "CE", "MLE", "OLE", "PE", "QLE", "SE", "IE"}:
        return {
            "verdict": status,
            "time_ms": time_ms,
            "memory_kb": memory_kb,
            "reason": reason,
            "feedback": feedback_text,
        }

    return {
        "verdict": status,
        "time_ms": time_ms,
        "memory_kb": memory_kb,
        "reason": reason,
        "feedback": feedback_text,
    }

