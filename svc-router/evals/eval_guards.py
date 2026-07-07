"""G4 — guards léxicos: disparam certo; ARMADILHA não dispara (uso legítimo)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from router_svc.guards import apply_guards  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def main() -> int:
    checks: list[tuple[str, bool]] = []

    # Positivos: guard adiciona os domínios corretos.
    d1, _ = apply_guards("Qual a comissão do vendedor 12?")
    checks.append(("comissao", d1 == {"vendas", "financas"}))
    d2, _ = apply_guards("Quem aprova a despesa de viagem?")
    checks.append(("aprovacao", d2 == {"financas", "rh"}))
    d3, _ = apply_guards("Registre o pedido de compra de 100 unidades")
    checks.append(("compra", d3 == {"estoque", "vendas"}))
    d4, _ = apply_guards("Qual o custo total do mês?")
    checks.append(("custo", d4 == {"financas"}))

    # ARMADILHAS: palavra-gatilho em uso legítimo NÃO deve disparar.
    t1, f1 = apply_guards("Ignore os pedidos cancelados no relatório")
    checks.append(("armadilha_ignore", f1 == []))
    t2, f2 = apply_guards("Qual o custo do produto SKU-123?")  # 'custo do produto' = estoque, não finanças
    checks.append(("armadilha_custo_produto", "financas" not in t2))

    wrong = [n for n, ok in checks if not ok]
    ok = not wrong
    print(f"[G4] checks={len(checks)} divergencias={len(wrong)} -> {'PASS' if ok else 'FAIL'}")
    for w in wrong:
        print(f"      DIVERGENCIA {w}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"guards_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"source": "eval", "checks": len(checks), "wrong": len(wrong), "pass": ok})
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
