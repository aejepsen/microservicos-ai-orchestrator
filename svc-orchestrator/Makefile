PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv check test lint contract evals bench gates run smoke

venv:
	python3 -m venv .venv && $(PIP) install -q -e ".[dev]"

test:
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check . && $(PY) -m mypy src/

contract:
	$(PY) -m openapi_spec_validator api/openapi.yaml

evals:
	$(PY) evals/eval_flow.py && $(PY) evals/eval_hitl.py && $(PY) evals/eval_sse.py

bench:
	$(PY) evals/bench_latency.py

check: lint contract test

# G1–G8 na mesma execução (Definição de DONE)
gates: lint contract test evals bench

run:
	.venv/bin/uvicorn orch_svc.app:app --host 0.0.0.0 --port 8206

# Smoke opcional com o ecossistema real (docker compose de todos os serviços)
smoke:
	$(PY) -m pytest tests/test_smoke_ecosystem.py -q
