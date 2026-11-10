"""Construção do LLM e chamadas com retry."""
from __future__ import annotations

import logging
import os
import time

log = logging.getLogger(__name__)

_USAGE = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0}


def reset_usage() -> None:
    for key in _USAGE:
        _USAGE[key] = 0


def get_usage() -> dict[str, int]:
    """Chamadas e tokens acumulados desde o último reset_usage() (0 se o provedor não informar)."""
    return dict(_USAGE)


def _record_usage(response) -> None:
    _USAGE["llm_calls"] += 1
    meta = getattr(response, "usage_metadata", None) or {}
    _USAGE["input_tokens"] += int(meta.get("input_tokens", 0) or 0)
    _USAGE["output_tokens"] += int(meta.get("output_tokens", 0) or 0)


def _require_env(var_name: str, provider: str) -> str:
    value = os.getenv(var_name)
    if value and value.strip():
        return value.strip()
    raise ValueError(
        f"Para usar o provider '{provider}', defina a variável {var_name} no .env ou no ambiente. "
        "As opções comuns são GOOGLE_API_KEY, OPENAI_API_KEY e NVIDIA_API_KEY."
    )


def _build_openai_compatible_llm(
    provider: str,
    model: str,
    max_tokens: int,
    *,
    reasoning_effort: str | None = None,
    api_key_env: str,
    base_url: str | None = None,
):
    api_key = _require_env(api_key_env, provider)
    from langchain_openai import ChatOpenAI
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "api_key": api_key,
    }
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def build_llm(
    provider: str,
    model: str,
    max_tokens: int,
    reasoning_effort: str | None = None,
):
    provider = (provider or "google").lower().replace("-", "_")
    if provider in {"openai"}:
        return _build_openai_compatible_llm(
            provider,
            model,
            max_tokens,
            reasoning_effort=reasoning_effort,
            api_key_env="OPENAI_API_KEY",
        )
    if provider in {"google", "gemini"}:
        _require_env("GOOGLE_API_KEY", provider)
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, max_output_tokens=max_tokens)
    if provider in {"nvidia", "nvidia_ai", "nvidia_ai_endpoints"}:
        api_key = _require_env("NVIDIA_API_KEY", provider)
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        return ChatNVIDIA(
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
        )
    raise ValueError(f"provider desconhecido: {provider}")


def message_text(content) -> str:
    """`.content` pode ser str ou lista de partes (comum em modelos Gemini/Claude)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in content)
    return str(content)


def _is_non_retryable(exc: Exception) -> bool:
    """Erros de autenticação/requisição inválida não se resolvem repetindo."""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    return status in {400, 401, 403, 404}


def invoke_with_retry(llm, prompt: str, retries: int = 3) -> str:
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None) or type(llm).__name__
    log.info("[LLM] iniciando chamada para modelo=%s, prompt_chars=%d, tentativas=%d", model_name, len(prompt), retries)
    for k in range(retries):
        try:
            response = llm.invoke(prompt)
            _record_usage(response)
            text = message_text(response.content)
            log.info("[LLM] resposta recebida do modelo=%s (tentativa=%d/%d, bytes=%d)", model_name, k + 1, retries, len(text))
            return text
        except Exception as e:  # rate limit, 5xx, timeout...
            log.warning("[LLM] falha no modelo=%s (tentativa=%d/%d): %s", model_name, k + 1, retries, e)
            if _is_non_retryable(e) or k == retries - 1:
                raise
            wait = 2 ** (k + 1)
            log.warning("[LLM] nova tentativa em %ss", wait)
            time.sleep(wait)
    raise RuntimeError("invoke_with_retry: retries deve ser >= 1")
