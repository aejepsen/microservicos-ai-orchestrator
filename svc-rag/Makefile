PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: venv check test lint contract evals bench gates run

venv:
	python3 -m venv .venv && $(PIP) install -q -e ".[dev]"

test:
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check . && $(PY) -m mypy src/

contract:
	$(PY) -m openapi_spec_validator api/openapi.yaml

evals:
	$(PY) evals/eval_chunking.py && $(PY) evals/eval_store.py && $(PY) evals/eval_recall.py

bench:
	$(PY) evals/bench_latency.py

check: lint contract test

# G1–G8 na mesma execução (Definição de DONE)
gates: lint contract test evals bench

run:
	.venv/bin/uvicorn rag_svc.app:app --host 0.0.0.0 --port 8204
