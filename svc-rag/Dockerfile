FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/models

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

# Baixa o embedder no build — boot sem rede, sem cold start.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

COPY api ./api

EXPOSE 8204
CMD ["uvicorn", "rag_svc.app:app", "--host", "0.0.0.0", "--port", "8204"]
