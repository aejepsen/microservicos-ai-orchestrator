"""Camada LLM: adapter HTTP OpenAI-compat (svc-inference) + FakeLLM determinístico.

Classifica a query nos domínios permitidos. Off por default; gates usam FakeLLM.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


class LLMClassifier(Protocol):
    def classify(self, query: str, allowed: list[str]) -> list[str]: ...


def _parse_domains(raw: str, allowed: list[str]) -> list[str]:
    match = _JSON_OBJ_RE.search(raw)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    got = data.get("domains", [])
    return [d for d in got if d in allowed]


class HttpLLM:
    """Cliente OpenAI-compat (chat/completions) para classificação."""

    def __init__(self, url: str, model: str, timeout_s: float = 30.0) -> None:
        self._url = url
        self._model = model
        self._timeout = timeout_s

    def classify(self, query: str, allowed: list[str]) -> list[str]:
        import httpx

        prompt = (
            f"Classifique a pergunta nos dominios permitidos {allowed}. "
            f'Responda JSON {{"domains": [...]}}.\nPergunta: {query}'
        )
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        resp = httpx.post(self._url, json=payload, timeout=self._timeout)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_domains(content, allowed)


class FakeLLM:
    """Determinístico para gates: devolve domínios pré-configurados (∩ allowed)."""

    def __init__(self, returns: list[str] | None = None) -> None:
        self._returns = returns

    def classify(self, query: str, allowed: list[str]) -> list[str]:
        if self._returns is not None:
            return [d for d in self._returns if d in allowed]
        return allowed[:1]  # fallback determinístico
