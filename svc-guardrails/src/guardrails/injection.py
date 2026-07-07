"""Detector de prompt injection: avaliação determinística do léxico PT-BR."""

from __future__ import annotations

from dataclasses import dataclass

from guardrails.patterns_pt import rules


@dataclass(frozen=True)
class InjectionVerdict:
    flagged: bool
    score: float
    patterns: list[str]


def detect_injection(text: str) -> InjectionVerdict:
    """Roda todas as famílias sobre o texto ORIGINAL (pré-sanitização)."""
    hits: list[tuple[str, float]] = [
        (rule.id, rule.weight) for rule in rules() if rule.pattern.search(text)
    ]
    if not hits:
        return InjectionVerdict(flagged=False, score=0.0, patterns=[])
    score = max(weight for _, weight in hits)
    return InjectionVerdict(flagged=True, score=score, patterns=[rid for rid, _ in hits])
