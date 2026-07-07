"""G3 — chunking: seções corretas, sem perda, sem corte de palavra, ARMADILHA."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_svc.chunking import chunk_document  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

DOC = """# Política de Reembolso

Despesas de viagem são reembolsadas em até 30 dias mediante nota fiscal.
O limite diário para alimentação é de cem reais por colaborador.

## Adiantamento

Adiantamentos exigem aprovação do gestor direto e do financeiro.

```
# Este não é um header de seção — está dentro de bloco de código
print("ola")
```
"""


def main() -> int:
    checks: list[tuple[str, bool]] = []
    chunks = chunk_document(DOC, max_chars=800, overlap=100)

    sections = {c.section for c in chunks}
    checks.append(("secoes_corretas", "Política de Reembolso" in sections and "Adiantamento" in sections))

    # ARMADILHA: header dentro de code fence NÃO vira seção
    checks.append(("armadilha_header_no_codigo", "Este não é um header de seção — está dentro de bloco de código" not in sections))

    # sem perda de conteúdo relevante
    joined = " ".join(c.text for c in chunks)
    checks.append(("conteudo_reembolso", "reembolsadas em até 30 dias" in joined))
    checks.append(("conteudo_adiantamento", "aprovação do gestor direto" in joined))

    # split por tamanho não corta palavra
    long_doc = "# S\n\n" + ("palavra " * 400)
    long_chunks = chunk_document(long_doc, max_chars=200, overlap=40)
    checks.append(("multiplos_chunks", len(long_chunks) > 1))
    checks.append(("sem_corte_palavra", all(not c.text.endswith("palavr") for c in long_chunks)))
    checks.append(("tamanho_respeitado", all(len(c.text) <= 200 for c in long_chunks)))

    wrong = [n for n, ok in checks if not ok]
    ok = not wrong
    print(f"[G3] checks={len(checks)} divergencias={len(wrong)} chunks={len(chunks)} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"chunking_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
