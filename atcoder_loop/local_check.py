"""Pré-checagem local: sintaxe + execução nos exemplos do enunciado.

O AtCoder só devolve o veredito; rodar os exemplos localmente gera feedback útil para o
reparo (traceback, saída esperada x obtida) e poupa submissões reais.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import LOCAL_TIMEOUT_S


def _norm(text: str) -> list[str]:
    return [line.rstrip() for line in text.strip().splitlines()]


def _is_equal(got: str, expected: str) -> bool:
    got_l, exp_l = _norm(got), _norm(expected)
    if got_l == exp_l:
        return True
    # tolera diferenças de espaçamento entre tokens (o AtCoder compara por tokens em geral)
    return got.split() == expected.split()


def check_samples(code: str, samples: list[tuple[str, str]], timeout: float = LOCAL_TIMEOUT_S) -> dict | None:
    """Devolve None se passou em tudo; senão um resultado no formato do juiz (verdict/feedback)."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"verdict": "CE", "time_ms": None, "memory_kb": None,
                "reason": f"SyntaxError: {e}", "feedback": f"SyntaxError: {e.msg} (line {e.lineno})"}

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "solution.py"
        path.write_text(code, encoding="utf-8")
        for n, (stdin, expected) in enumerate(samples, 1):
            try:
                proc = subprocess.run([sys.executable, "-I", str(path)], input=stdin, text=True,
                                      capture_output=True, timeout=timeout, cwd=tmp)
            except subprocess.TimeoutExpired:
                msg = f"Sample {n}: timed out after {timeout:.0f}s.\nInput:\n{stdin}"
                return {"verdict": "TLE", "time_ms": None, "memory_kb": None, "reason": msg, "feedback": msg}
            if proc.returncode != 0:
                msg = f"Sample {n}: runtime error (exit {proc.returncode}).\nInput:\n{stdin}\nStderr:\n{proc.stderr[-1000:]}"
                return {"verdict": "RE", "time_ms": None, "memory_kb": None, "reason": msg, "feedback": msg}
            if not _is_equal(proc.stdout, expected):
                msg = (f"Sample {n}: wrong answer.\nInput:\n{stdin}\nExpected output:\n{expected}\n"
                       f"Your output:\n{proc.stdout[-500:]}")
                return {"verdict": "WA", "time_ms": None, "memory_kb": None, "reason": msg, "feedback": msg}
    return None
