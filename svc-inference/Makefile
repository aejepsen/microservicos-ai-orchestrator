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
	$(PY) evals/eval_openai_compat.py && $(PY) evals/eval_usage.py && $(PY) evals/eval_resilience.py

bench:
	$(PY) evals/bench_latency.py

check: lint contract test

# G1–G8 na mesma execução (Definição de DONE)
gates: lint contract test evals bench

run:
	.venv/bin/uvicorn inference.app:app --host 0.0.0.0 --port 8202

# Smoke opcional com Ollama real (exige Ollama no ar + BACKEND=ollama)
smoke:
	BACKEND=ollama $(PY) -m pytest tests/test_smoke_ollama.py -q
