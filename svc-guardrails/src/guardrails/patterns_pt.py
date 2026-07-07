"""Léxico PT-BR de prompt injection — 12 famílias versionadas em código.

Princípio anti-falso-positivo: regra dispara só com CONTEXTO adversarial
(verbo imperativo + objeto-instrução como "instruções/regras/prompt"),
nunca com palavra solta. "Ignore os pedidos cancelados" é uso legítimo;
"ignore as instruções anteriores" não é.

A detecção roda sobre o texto ORIGINAL (pré-sanitização): delimitadores
neutralizados pela sanitização continuam sendo evidência de ataque.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Objetos-instrução: alvo legítimo de um ataque, nunca de pergunta de negócio.
_INSTR = (  # noqa: E501 — regex único; quebrar prejudica legibilidade da alternância
    r"(?:instru[cç][oõ]es|regras|diretrizes|prompt(?:\s+do\s+sistema)?|system\s*prompt"
    r"|pol[ií]ticas\s+do\s+sistema|configura[cç][aã]o\s+inicial|comandos\s+anteriores)"
)


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    pattern: re.Pattern[str]
    weight: float = 1.0


_RULES: list[Rule] = [
    Rule(
        "ignore_instructions",
        "Ordem de ignorar/descartar as instruções do sistema",
        re.compile(
            rf"\b(?:ignore|desconsidere|esque[cç]a|descarte|desative)\b[\s\S]{{0,40}}?\b(?:(?:as|suas|todas\s+as)\s+)?{_INSTR}",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "persona_override",
        "Redefinição de persona do assistente",
        re.compile(
            r"\b(?:agora\s+voc[eê]\s+[eé]\b|finja\s+(?:ser|que\s+[eé])|assuma\s+o\s+papel\s+de|voc[eê]\s+n[aã]o\s+[eé]\s+mais\s+(?:um|uma|o|a)\b|aja\s+como\s+se\s+(?:n[aã]o\s+houvesse|voc[eê]\s+n[aã]o\s+tivesse))",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "false_authority",
        "Falsa autoridade emitindo ordem privilegiada",
        re.compile(
            r"\b(?:sou|como|aqui\s+[eé])\s+(?:o\s+|a\s+|seu\s+|sua\s+)?(?:administrador(?:a)?|desenvolvedor(?:a)?|criador(?:a)?|dono\s+do\s+sistema|suporte\s+t[eé]cnico|engenheiro\s+respons[aá]vel)\b[\s\S]{0,80}?\b(?:ordeno|exijo|autorizo|determino|libere|desative|desabilite|ignore|revele)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "prompt_exfiltration",
        "Pedido de revelação do prompt/instruções internas",
        re.compile(
            rf"\b(?:repita|mostre|revele|imprima|exiba|liste|transcreva|copie)\b[\s\S]{{0,40}}?\b(?:o\s+|as\s+|suas?\s+|seu\s+)?(?:{_INSTR}|texto\s+inicial|mensagem\s+de\s+sistema)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "chat_delimiters",
        "Delimitadores de template de chat embutidos no input",
        re.compile(
            r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[/?INST\]|<<SYS>>|(?:^|\n)\s*#{0,4}\s*(?:system|sistema)\s*:",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "encoding_payload",
        "Instrução para decodificar/executar payload codificado",
        re.compile(
            r"\b(?:decodifique|decode|interprete)\b[\s\S]{0,40}?\b(?:base64|hex|bin[aá]rio)\b|\bexecute\s+o\s+(?:c[oó]digo|comando)\s+(?:codificado|abaixo|oculto)\b",
            re.IGNORECASE,
        ),
        weight=0.9,
    ),
    Rule(
        "rule_violation",
        "Ordem explícita de violar/contornar regras ou filtros",
        re.compile(
            rf"\b(?:sem\s+seguir|ignorando|violando|contorne|burle|desrespeite|n[aã]o\s+siga)\b[\s\S]{{0,40}}?\b(?:(?:as|a|os|suas?)\s+)?(?:{_INSTR}|pol[ií]tica(?:s)?|restri[cç][oõ]es|filtros|limites\s+de\s+seguran[cç]a)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "jailbreak_mode",
        "Ativação de modo irrestrito / jailbreak clássico",
        re.compile(
            r"\bmodo\s+(?:dan|desenvolvedor|deus|irrestrito|sem\s+censura|sem\s+filtro)\b|\bvoc[eê]\s+(?:n[aã]o\s+tem|est[aá]\s+livre\s+de)\s+(?:filtros|restri[cç][oõ]es|censura|limites)\b|\bjailbreak\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "instruction_update",
        "Tentativa de reescrever as instruções/comportamento do assistente",
        re.compile(
            rf"\b(?:atualize|adicione|substitua|reescreva|sobrescreva|anexe)\b[\s\S]{{0,40}}?\b(?:(?:em|a|ao|às?)\s+)?(?:suas?\s+|seu\s+)?(?:{_INSTR}|persona|comportamento\s+padr[aã]o)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "privilege_escalation",
        "Alegação/concessão de privilégio elevado",
        re.compile(
            r"\bvoc[eê]\s+(?:tem|recebeu|ganhou)\s+(?:permiss[aã]o|acesso)\s+(?:total|root|admin(?:istrativo)?|irrestrito)\b|\bacesso\s+(?:root|admin)\s+concedido\b|\beleve\s+(?:suas|as)\s+permiss[oõ]es\b|\bprivil[eé]gios\s+de\s+administrador\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "context_reset",
        "Reset adversarial de contexto/memória",
        re.compile(
            r"\besque[cç]a\s+tudo\s+(?:acima|anterior|que\s+foi\s+dito|at[eé]\s+aqui)\b|\bnova\s+conversa\s*[:.]\s|\breinicie\s+(?:sua\s+mem[oó]ria|o\s+contexto)\b|\bapague\s+(?:seu\s+hist[oó]rico|sua\s+mem[oó]ria)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "bulk_exfiltration",
        "Exfiltração em massa de dados sensíveis",
        re.compile(
            r"\b(?:envie|liste|exporte|despeje|me\s+d[eê]|revele)\b[\s\S]{0,40}?\b(?:todas\s+as\s+senhas|todos\s+os\s+sal[aá]rios\s+de\s+todos|todo\s+o\s+banco\s+de\s+dados|todos\s+os\s+dados\s+(?:pessoais|confidenciais|sigilosos))\b|\bdump\s+(?:do\s+banco|da\s+tabela|completo)\b",
            re.IGNORECASE,
        ),
    ),
]


def rules() -> list[Rule]:
    return list(_RULES)
