"""Utilitários compartilhados pelos grafos de geração."""
from __future__ import annotations

import ast
import re

FENCE_RE = re.compile(r"```[ \t]*([\w+#-]*)[ \t]*\r?\n(.*?)\r?\n?```", re.DOTALL)
_PY_TAGS = {"python", "python3", "py"}


def _is_valid_python(text: str) -> bool:
    try:
        ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    return bool(text.strip())


def extract_code(text: str) -> str:
    """Extrai o último bloco Python da resposta, inclusive fences truncadas."""
    text = text or ""
    blocks = FENCE_RE.findall(text)
    tagged = [code for tag, code in blocks if tag.lower() in _PY_TAGS and code.strip()]
    if tagged:
        return tagged[-1].strip() + "\n"
    untagged = [code for tag, code in blocks if not tag and _is_valid_python(code)]
    if untagged:
        return untagged[-1].strip() + "\n"
    match = re.search(r"```[ \t]*(?:python3?|py)?[ \t]*\r?\n(.*)$", text, re.DOTALL | re.IGNORECASE)
    candidate = match.group(1) if match else text
    candidate = re.sub(r"\r?\n```\s*$", "", candidate).strip()
    return candidate + "\n" if _is_valid_python(candidate) else ""
