# Deployment — AI-Orchestrator Microsserviços

Deploy single-node via Docker Compose. Requer Docker + Docker Compose v2 e (para o
chat com LLM) uma GPU NVIDIA com o runtime container configurado.

## Pré-requisitos

- Docker Engine 24+ com Compose v2 (`docker compose version`)
- GPU NVIDIA + `nvidia-container-toolkit` (para `svc-inference`/Ollama). Sem GPU o
  stack sobe, mas a geração LLM roda em CPU (lenta) — ver `docs/RUNBOOK.md`.
- Volume Ollama com o modelo `qwen3.5-9b-orch` (compartilhado com o AI-Orchestrator,
  `ai-orchestrator_ollama_data`). Sem ele: `make model` após subir.

## 1. Configurar segredos

```bash
cp .env.example .env
# edite .env — gere chaves fortes:
#   INTERNAL_KEY   : openssl rand -hex 32   (auth interna entre serviços)
#   QDRANT_API_KEY : openssl rand -hex 24
#   GRAFANA_PASSWORD: senha forte do admin do Grafana
#   MODEL          : qwen3.5-9b-orch  (default)
```

O stack é **fail-closed**: sem `INTERNAL_KEY`/`QDRANT_API_KEY`/`GRAFANA_PASSWORD` no
`.env`, o `docker compose` recusa subir (`${VAR:?}`). `.env` está no `.gitignore` —
nunca é commitado.

## 2. Subir o stack

```bash
make up          # docker compose -f docker-compose.prod.yml up -d --build
make ps          # status; aguarde todos "healthy"
```

Ordem de boot é resolvida por `depends_on: service_healthy` — o orchestrator só sobe
após guardrails/router/rag/inference/observability estarem saudáveis.

## 3. Validar

```bash
make smoke-test  # 10 asserts: health, ingest RAG, chat RAG+LLM, SSE, 403/401,
                 # trace no Jaeger (5 serviços), Prometheus, Grafana
```

Verde = deploy bom. O smoke ingere um doc golden e faz um chat real com o LLM.

## 4. Acessar

| UI | URL | Credencial |
|----|-----|------------|
| Chat (API) | http://127.0.0.1:8206/v1/chat | header `X-Internal-Key` |
| Grafana | http://127.0.0.1:3000 | `admin` / `$GRAFANA_PASSWORD` |
| Jaeger (traces) | http://127.0.0.1:16686 | — |
| Prometheus | http://127.0.0.1:9090 | — |

Exemplo de chamada:

```bash
source .env
curl -s -X POST http://127.0.0.1:8206/v1/chat \
  -H "X-Internal-Key: $INTERNAL_KEY" -H 'Content-Type: application/json' \
  -d '{"query": "Qual o faturamento total do trimestre?"}'
```

## 5. Operação do dia a dia

```bash
make logs        # logs agregados (follow)
make backup      # snapshot do Qdrant -> ./backups (agende via cron p/ RPO)
make down        # derruba, mantém volumes (dados preservados)
make clean       # derruba E APAGA volumes — destrutivo
```

## Imagens

O CI (`.github/workflows/ci.yml`) publica cada serviço no GHCR a cada push na
`master`: `ghcr.io/aejepsen/svc-*:<sha>` e `:latest`. Para deploy a partir das
imagens publicadas (em vez de `--build` local), aponte cada serviço para a imagem
GHCR — o compose já nomeia `image: msvc-prod-svc-*:latest` para build local.

## Rollback

Stateless: reverter é redeploy da imagem anterior.

```bash
git checkout <sha-anterior> -- docker-compose.prod.yml
make up
```

Dados (Qdrant) não são afetados por rollback de imagem. Se precisar reverter dados:
`make restore DIR=backups/<timestamp>` (ver `docs/RUNBOOK.md`).

## Notas de produção externa (fora do escopo single-node)

Para expor além de `localhost`: colocar um reverse proxy (nginx/Caddy) com TLS na
frente do `:8206`, terminar HTTPS ali, e manter os serviços na rede interna. A Fase 11
(Kubernetes/ingress/cert-manager) foi skipped — este stack cobre single-node.
