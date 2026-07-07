"""LLM-judge adapter (opcional) + scorer llm_judge.

svc-evals NÃO serve modelo (isso é svc-inference). O juiz fala HTTP com um
endpoint OpenAI-compatível/Ollama, desligado por default. Determinismo:
temperature=0, format=json, parse tolerante a lixo em volta do JSON.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from evals_svc.scorers import Case, ScoreResult

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_verdict(raw: str) -> dict[str, Any]:
    """Extrai o primeiro objeto JSON de uma resposta possivelmente suja."""
    match = _JSON_OBJ_RE.search(raw)
    if not match:
        raise ValueError("nenhum JSON na resposta do juiz")
    return json.loads(match.group(0))


class Judge(Protocol):
    def judge(self, prompt: str) -> dict[str, Any]: ...


class HttpJudge:
    """Cliente para endpoint OpenAI-compatível (chat/completions)."""

    def __init__(self, url: str, model: str, timeout_s: float) -> None:
        self._url = url
        self._model = model
        self._timeout = timeout_s

    def judge(self, prompt: str) -> dict[str, Any]:
        import httpx

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        resp = httpx.post(self._url, json=payload, timeout=self._timeout)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return parse_verdict(content)


class FakeJudge:
    """Juiz determinístico para testes/dogfood: fiel se resposta contém a evidência."""

    def judge(self, prompt: str) -> dict[str, Any]:
        # Convenção do golden-espelho: prompt traz "EVIDENCIA: <x>" e "RESPOSTA: <y>".
        evidences = re.findall(r"EVIDENCIA:\s*(.+)", prompt)
        answers = re.findall(r"RESPOSTA:\s*(.+)", prompt)
        ev = evidences[0].strip().lower() if evidences else ""
        ans = answers[0].strip().lower() if answers else ""
        faithful = bool(ev) and ev in ans
        return {"faithful": faithful, "reason": "fake-deterministic"}


def score_llm_judge(case: Case, response: Any, params: dict[str, Any]) -> ScoreResult:
    """Requer judge em params['_judge']. Constrói prompt e interpreta veredito."""
    judge: Judge | None = params.get("_judge")
    if judge is None:
        raise RuntimeError("llm_judge sem adapter (JUDGE_ENABLED=0)")
    evidence = case.get("evidence", case.get("expected", ""))
    prompt = (
        f"Avalie fidelidade.\nEVIDENCIA: {evidence}\nRESPOSTA: {response}\n"
        "Responda JSON {faithful: bool}."
    )
    verdict = judge.judge(prompt)
    ok = bool(verdict.get("faithful", False))
    return ScoreResult(ok, 1.0 if ok else 0.0)
