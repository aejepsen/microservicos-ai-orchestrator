FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

COPY api ./api

EXPOSE 8206
# SEC-01 (FASE 13): non-root. Modelos/dirs já criados como root acima; chown antes de trocar.
RUN useradd -r -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "orch_svc.app:app", "--host", "0.0.0.0", "--port", "8206"]
