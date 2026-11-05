"""Entrada e saída em disco: CSV de ids, CSV de resultados e arquivos de tentativas."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from taes.core.config import RESULT_FIELDS


def compact_text(value: object, limit: int = 1200) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ... [truncado]"


def read_ids(csv_path: str) -> list[str]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "problem_id" not in (reader.fieldnames or []):
            raise SystemExit(f"{csv_path}: coluna `problem_id` não encontrada (achei {reader.fieldnames}).")
        ids = [r["problem_id"].strip() for r in reader if (r["problem_id"] or "").strip()]
    return list(dict.fromkeys(ids))  # remove duplicados preservando a ordem


def load_previous(out_csv: str) -> dict[str, dict]:
    if not Path(out_csv).exists():
        return {}
    with open(out_csv, encoding="utf-8", newline="") as f:
        return {r["problem_id"]: r for r in csv.DictReader(f)}


def write_results(out_csv: str, rows: dict[str, dict]) -> None:
    keys = []
    seen = set()
    for field in RESULT_FIELDS:
        if field not in seen:
            keys.append(field)
            seen.add(field)
    for row in rows.values():
        for key in row.keys():
            if key not in seen:
                keys.append(key)
                seen.add(key)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for row in rows.values():
            sanitized = {}
            for key in keys:
                value = row.get(key)
                if key in {"reason", "feedback"}:
                    sanitized[key] = compact_text(value)
                else:
                    sanitized[key] = value
            w.writerow(sanitized)


def write_error_rows(out_csv: str, rows: dict[str, dict]) -> None:
    relevant = {
        pid: row for pid, row in rows.items()
        if row.get("verdict") not in {None, "AC"} and (row.get("reason") or row.get("feedback"))
    }
    if not relevant:
        Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
        Path(out_csv).write_text("problem_id,verdict,reason,feedback\n", encoding="utf-8")
        return

    keys = ["problem_id", "verdict", "reason", "feedback"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for pid, row in relevant.items():
            w.writerow({
                "problem_id": pid,
                "verdict": row.get("verdict", ""),
                "reason": row.get("reason", ""),
                "feedback": row.get("feedback", ""),
            })


def save_attempt(att_dir: Path, entry: dict) -> None:
    """Salva uma tentativa: attemptN.py (código) e attemptN.json (prompt, resposta bruta, resultado)."""
    att_dir.mkdir(parents=True, exist_ok=True)
    n = entry["attempt"]
    (att_dir / f"attempt{n}.py").write_text(entry["code"], encoding="utf-8")
    (att_dir / f"attempt{n}.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")


def save_solution(out_dir: Path, problem_id: str, code: str) -> None:
    (out_dir / f"{problem_id}.py").write_text(code, encoding="utf-8")
