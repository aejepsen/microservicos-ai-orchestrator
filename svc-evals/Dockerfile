FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

COPY api ./api

EXPOSE 8201
CMD ["uvicorn", "evals_svc.app:app", "--host", "0.0.0.0", "--port", "8201"]
