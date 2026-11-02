"""Construção do LLM e chamadas com retry."""
from __future__ import annotations

import logging
import os
import time

log = logging.getLogger(__name__)


def _require_env(var_name: str, provider: str) -> str:
    value = os.getenv(var_name)
    if value and value.strip():
        return value.strip()
    raise ValueError(
        f"Para usar o provider '{provider}', defina a variável {var_name} no .env ou no ambiente. "
        f"Se quiser usar Gemini/Google, configure GOOGLE_API_KEY."
    )


def build_llm(provider: str, model: str, temperature: float, max_tokens: int):
    provider = (provider or "google").lower()
    if provider == "openai":
        _require_env("OPENAI_API_KEY", provider)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, max_tokens=max_tokens)
    if provider == "google":
        _require_env("GOOGLE_API_KEY", provider)
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, temperature=temperature, max_output_tokens=max_tokens)
    raise ValueError(f"provider desconhecido: {provider}")


def message_text(content) -> str:
    """`.content` pode ser str ou lista de partes (comum em modelos Gemini/Claude)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in content)
    return str(content)


def invoke_with_retry(llm, prompt: str, retries: int = 3) -> str:
    for k in range(retries):
        try:
            return message_text(llm.invoke(prompt).content)
        except Exception as e:  # rate limit, 5xx, timeout...
            if k == retries - 1:
                raise
            wait = 2 ** (k + 1)
            log.warning("LLM falhou (%s); nova tentativa em %ss", e, wait)
            time.sleep(wait)
    return ""
