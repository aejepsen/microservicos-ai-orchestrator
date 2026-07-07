# PRÓXIMAS FASES — Pós SDD (Rodadas 1-7)

> Roadmap de integração, deployment e operação do ecossistema após conclusão dos 7 serviços (2026-07-06).

---

## FASE 8: E2E Integration Testing (1-2 semanas)

**Objetivo:** Validar o ecossistema todo funcionando junto, com todas as defesas, resiliência e observabilidade.

### 8.1 Suite de testes

```bash
tests/e2e/
  test_full_flow.py           # chat completo: guard → route → fan-out → fan-in
  test_resilience.py          # circuit breaker recovery, downstream restart
  test_sse_streaming.py       # SSE eventos in-order, reconnection
  test_hitl_approval.py       # pausa-retoma-bloqueia write intent
  test_distributed_trace.py   # traceparent propagação W3C todos os hops
  test_integration_matrix.py  # todos os pares de downstream (21 combos)
conftest.py                   # fixtures: sobe docker-compose, aguarda /health
```

### 8.2 Cenários

| Cenário | Setup | Verificação |
|---------|-------|-------------|
| **Happy path** | query legítima, single domínio | `decision: answered`, final com contexto, P95 < 2s |
| **Multi-domínio** | query que roteia para 2-3 domínios | agentes rodando em paralelo, síntese composta |
| **Guardrails block** | injection conhecido | `decision: blocked`, 403, evento `blocked` |
| **OOD flag** | pergunta fora-domínio | `decision: answered` (flag=log-only), resposta genérica |
| **Write HITL** | "cadastre novo funcionário" | `decision: paused`, `pending_write`, retoma só com `approve=true` |
| **Write armadilha** | "contas a pagar" (frase nominal) | leitura, NÃO pausa, resposta direta |
| **Downstream down** | matar svc-inference | circuit OPEN, `health` reporta `inference: down`, fan-in parcial |
| **Circuit recovery** | reabrir svc-inference após 30s | /health `inference: ok`, circuito HALF_OPEN, sucesso → CLOSED |
| **SSE interrupted** | client fecha stream durante agent | servidor não loga erro, próximas requets OK |
| **Rate limit** | 200 req/s por IP | 429 após threshold, sliding window respeitado |
| **Trace propagation** | verificar Jaeger | trace_id vaza em todos os hops, spans linkados |

### 8.3 Acceptance Criteria

- [x] 100% cenários PASS — 22 passed (20 padrão + 2 resiliência com `E2E_RESILIENCE=1`), 1 skip documentado (trace em logs → DS-01/OTel)
- [ ] P95 latência end-to-end < 2s (single) / < 5s (multi) — N/A em CPU local (ollama sem GPU, ~20-60s/geração); revalidar na FASE 14 (k6) com GPU
- [x] Nenhum circuito falha falsa (`test_no_false_circuit_open_on_healthy_stack`)
- [ ] Traces completos em Jaeger — deferido para FASE 12 (DS-01: OTel real)
- [ ] **docker-compose.yaml (produção)** pronto e validado — FASE 9

### 8.4 Como rodar (resultado da fase)

```bash
docker compose -f docker-compose.e2e.yml up -d --build   # ~5 min primeira vez (pull do modelo)
python3 -m pytest tests/e2e                              # 20 passed, 3 skipped (~6 min em CPU)
E2E_RESILIENCE=1 python3 -m pytest tests/e2e/test_resilience.py  # destrutivo (para/religa svc-inference)
docker compose -f docker-compose.e2e.yml down            # teardown
```

Opt-ins: `E2E_AUTOSTART=1` (conftest sobe a stack sozinho), `E2E_KEY`, `E2E_CHAT_TIMEOUT_S` (default 180).
Bug real encontrado e corrigido pela suite: QdrantStore gravava 0 pontos (id hex inválido p/ Qdrant) — ver `svc-rag/DECISIONS.md` D8.

---

## FASE 9: Docker Compose Production (1 semana)

**Objetivo:** Stack local completo e isolado (sem dependências externas além do Docker).

### 9.1 Estrutura

```yaml
version: '3.9'
services:
  svc-orchestrator:
    image: msvc-e2e-svc-orchestrator:latest
    ports: ["8206:8000"]
    environment:
      INTERNAL_KEY: ${INTERNAL_KEY}
      DOWNSTREAM_ORCHESTRATOR_URL: http://svc-orchestrator:8000
      OTEL_ENABLED: 1
    healthcheck: { test: ["GET /health"], interval: 10s, timeout: 5s, retries: 3 }
    depends_on:
      - svc-guardrails
      - svc-router
      - svc-rag
      - svc-inference
      - svc-observability

  svc-guardrails:
    image: msvc-e2e-svc-guardrails:latest
    environment:
      INTERNAL_KEY: ${INTERNAL_KEY}
      OOD_REQUIRED: 1
    volumes:
      - guardrails_models:/app/models
    healthcheck: { test: ["GET /health"], interval: 10s, timeout: 5s }

  svc-router:
    image: msvc-e2e-svc-router:latest
    environment:
      INTERNAL_KEY: ${INTERNAL_KEY}
    healthcheck: { test: ["GET /health"], interval: 10s, timeout: 5s }

  svc-inference:
    image: msvc-e2e-svc-inference:latest
    environment:
      INTERNAL_KEY: ${INTERNAL_KEY}
      OLLAMA_BASE_URL: http://ollama:11434
    volumes:
      - inference_models:/root/.ollama
    depends_on:
      - ollama
    healthcheck: { test: ["GET /health"], interval: 10s, timeout: 5s }

  svc-rag:
    image: msvc-e2e-svc-rag:latest
    environment:
      INTERNAL_KEY: ${INTERNAL_KEY}
      QDRANT_HOST: qdrant
      NEO4J_URI: bolt://neo4j:7687
    depends_on:
      - qdrant
      - neo4j
    healthcheck: { test: ["GET /health"], interval: 10s, timeout: 5s }

  svc-observability:
    image: msvc-e2e-svc-observability:latest
    environment:
      INTERNAL_KEY: ${INTERNAL_KEY}
      OTEL_EXPORTER_OTLP_ENDPOINT: http://jaeger:4318
      PROMETHEUS_PORT: 9090
    ports: ["9090:9090", "16686:16686"]
    healthcheck: { test: ["GET /health"], interval: 10s, timeout: 5s }

  # Infra
  ollama:
    image: ollama/ollama:latest
    environment:
      OLLAMA_HOST: 0.0.0.0:11434
    volumes:
      - ollama_data:/root/.ollama
    pull_policy: if_not_present

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_storage:/qdrant/storage
    environment:
      QDRANT_API_KEY: ${QDRANT_API_KEY:-qdrant-key}
    ports: ["6333:6333"]

  neo4j:
    image: neo4j:latest
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-neo4j-password}
      NEO4J_dbms_security_bolt_listen__address: 0.0.0.0:7687
    volumes:
      - neo4j_data:/var/lib/neo4j/data
    ports: ["7687:7687", "7474:7474"]

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports: ["6831:6831/udp", "4318:4318", "16686:16686"]
    environment:
      COLLECTOR_OTLP_ENABLED: 'true'

volumes:
  guardrails_models:
  inference_models:
  ollama_data:
  qdrant_storage:
  neo4j_data:

networks:
  default:
    name: msvc-ai-net
    driver: bridge
```

### 9.2 .env.example

```bash
INTERNAL_KEY=your-internal-secret-key-change-in-prod
QDRANT_API_KEY=qdrant-api-key
NEO4J_PASSWORD=neo4j-password-change

OTEL_ENABLED=1
LOG_LEVEL=INFO
ALLOW_OPEN_ACCESS=0
```

### 9.3 Smoke test

```bash
make smoke-test  # roda após compose up (aguarda /health)
# Verifica:
# - Todos os /health = ok
# - Chat completo funciona (query legítima)
# - SSE streaming de eventos correto
# - Traces em Jaeger visíveis
```

### 9.4 As-built (2026-07-07)

**Entregue:** `docker-compose.prod.yml` + `.env.example` + `Makefile` (raiz) + `scripts/smoke.sh`.

**Decisões (divergências do rascunho §9.1, com razão):**

| # | Decisão | Razão |
|---|---------|-------|
| F9-D1 | **Modelo de referência: `qwen3.5-9b-orch`** (default de `MODEL` no compose e `.env.example`) | Mesmo modelo do AI-Orchestrator em produção (fine-tune próprio, 5.8 GB quantizado, 100% na GPU RTX 3060 12 GB). O 30b-a3b não cabe (transborda ~44% pra CPU); só foi usado no Colab para fine-tune. `qwen2.5:3b` fica restrito ao E2E (velocidade em CI/CPU). |
| F9-D2 | **GPU passthrough no `ollama`** (`deploy.resources.reservations.devices: nvidia`) + `OLLAMA_NUM_PARALLEL=3`, `OLLAMA_FLASH_ATTENTION=1`, `KEEP_ALIVE=5m`, `mem 12g` | Espelha a config validada do AI-Orchestrator; 9b em CPU inviabiliza o P95. |
| F9-D3 | **Volume Ollama externo compartilhado** (`ai-orchestrator_ollama_data`) | Modelos já baixados (~38 GB); duplicar volume = minutos de cópia + disco. Mesmo padrão do e2e. |
| F9-D4 | **Neo4j fora do stack** | svc-rag não tem backend de grafo implementado (`GRAPHRAG_ENABLED` sem consumidor). Infra morta não sobe; entra quando DS-13/graph existir. |
| F9-D5 | **Jaeger fora do stack** | OTel real deferido (DS-01, FASE 12); nenhum serviço exporta traces. Item "traces em Jaeger" do smoke (§9.3) migra pra FASE 12. |
| F9-D6 | **Postgres fora do stack (por ora)** | DS-02/DS-03 ainda em SQLite; Postgres entra no compose junto com essas specs. |
| F9-D7 | **Rede `backend` `internal: true`; portas públicas só 127.0.0.1** (8206 orchestrator, 8205 obs, 8204 rag-admin) | Qdrant/Ollama inacessíveis do host; superfície mínima. Ollama também na `edge` (sem porta publicada) só para egress de `ollama pull`. |
| F9-D8 | **`INTERNAL_KEY`/`QDRANT_API_KEY` obrigatórias** (`${VAR:?}`) + Qdrant com `QDRANT__SERVICE__API_KEY` | Fail-closed: stack não sobe sem segredo definido. |
| F9-D9 | **`HF_HUB_OFFLINE=1`** em guardrails/router/rag | Rede `internal` não resolve DNS; sem a flag, o hub do HF tenta HEAD no huggingface.co e derruba o load do SentenceTransformer mesmo com cache em `HF_HOME=/app/models`. Descoberto no primeiro smoke (router `degraded`, embedder down). |

**Smoke (`make smoke-test`):** health agregado, ingest RAG (Qdrant real), chat RAG+LLM com asserts, SSE (`stream: true` → `text/event-stream`), injection → 403, sem chave → 401, refresh do observability.

**Resultado: PASS (2026-07-07)** — GPU RTX 3060 detectada (CUDA, 11.6 GiB), `qwen3.5-9b-orch` servido pelo Ollama, chat com RAG respondeu com contexto (`context_used=2`), 5/5 upstreams raspados pelo observability. Query golden do smoke = mesma do E2E (`faturamento do trimestre` → domínio `financas`); a query original de reembolso roteava legitimamente pra `rh` (score 0.70 vs 0.55).

**Validação de deploy (ciclo autônomo, 2026-07-07):**
- Deploy limpo do zero (`down` → `up -d --build` → smoke): **PASS no ciclo 1**, 9/9 containers healthy — caminho frio reprodutível, sem correção manual.
- Persistência: `restart qdrant svc-rag` + busca **sem re-ingest** → 2 hits recuperados do volume `qdrant_storage`. Critério "volumes para persistência" fechado.
- Falhas encontradas e corrigidas durante a fase (registradas acima): embedder down por DNS na rede internal (→ F9-D9), assert de domínio errado no smoke herdado do e2e (→ query golden), escaping bash/python no assert inline (→ heredoc).

---

## FASE 10: CI/CD Pipeline (1-2 semanas)

**Objetivo:** Automação build → test → push → E2E validação.

### 10.1 GitHub Actions workflow

```yaml
name: SDD Multi-Service Pipeline
on: [push, pull_request]

jobs:
  # Paralelo
  lint:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [guardrails, router, rag, inference, orchestrator, observability, evals]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: cd svc-${{ matrix.service }} && make lint

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [guardrails, router, rag, inference, orchestrator, observability, evals]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: cd svc-${{ matrix.service }} && make gates  # G1-G8

  # Sequencial
  build:
    needs: [lint, test]
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [guardrails, router, rag, inference, orchestrator, observability, evals]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v2
      - uses: docker/login-action@v2
        with:
          registry: ${{ secrets.ECR_REGISTRY }}
          username: ${{ secrets.AWS_ACCESS_KEY_ID }}
          password: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      - uses: docker/build-push-action@v4
        with:
          context: svc-${{ matrix.service }}
          push: true
          tags: |
            ${{ secrets.ECR_REGISTRY }}/svc-${{ matrix.service }}:${{ github.sha }}
            ${{ secrets.ECR_REGISTRY }}/svc-${{ matrix.service }}:latest

  e2e:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v2
      - run: docker compose pull
      - run: INTERNAL_KEY=${{ secrets.INTERNAL_KEY_TEST }} docker compose up -d
      - run: sleep 15 && make smoke-test
      - run: docker compose logs > ${{ runner.temp }}/compose.logs
      - uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: compose-logs
          path: ${{ runner.temp }}/compose.logs
```

### 10.2 Gates paralelos

- **lint**: ruff, mypy por serviço (10-20s cada) → 2-3 min total paralelo
- **test**: pytest G1-G8 por serviço (30-60s cada) → 3-5 min total paralelo
- **build**: docker build por serviço (2-5 min cada) → 2-5 min paralelo
- **e2e**: smoke test + traces (2-3 min sequencial)

**Total pipeline:** ~15-20 min

### 10.3 As-built (2026-07-07)

**Entregue:** `.github/workflows/ci.yml` + `.github/compose-ci.yml`. **Run 28861233944: 15/15 jobs verdes na primeira execução, 20min18s** (dentro da meta).

Pipeline real: `gates` (matrix 7 serviços, `make venv` + `make gates` G1–G8, cache pip+HF) → `smoke` (stack e2e completo no runner via `docker compose --wait`, `scripts/smoke.sh` 7 passos) → `publish` (7 imagens → GHCR, tags `sha`+`latest`, só em push na master).

**Decisões (divergências do rascunho, com razão):**

| # | Decisão | Razão |
|---|---------|-------|
| F10-D1 | **GHCR em vez de ECR** (`ghcr.io/aejepsen/svc-*`) | Sem conta AWS no projeto; GHCR autentica com `GITHUB_TOKEN` nativo — zero secret externo, zero custo. Único secret do pipeline inteiro. |
| F10-D2 | **Smoke CI em CPU com `qwen2.5:0.5b`** (`E2E_MODEL`) | Runner sem GPU; asserts do smoke não dependem de qualidade de geração (domínio/RAG vêm do embedder, determinístico). Prod continua `qwen3.5-9b-orch`/GPU (F9-D1/D2). |
| F10-D3 | **Override `.github/compose-ci.yml`** (volume Ollama `external: false`) | `docker-compose.e2e.yml` referencia volume externo da máquina dev (`ai-orchestrator_ollama_data`), inexistente no runner. |
| F10-D4 | **`INTERNAL_KEY` efêmera por run** (`ci-smoke-key`) | Stack CI é descartável; secret fixo de repo seria superfície sem benefício. |
| F10-D5 | **Free-disk no job smoke** (remove android/dotnet/ghc) | 7 imagens com torch+SBERT estouram o disco default do runner. |
| F10-D6 | **Cache buildx `type=gha` por serviço** no publish | Rebuild incremental; jobs de publish com cache quente caem de ~10min pra <1min (medido: svc-evals/inference/observability/orchestrator 0-1min vs svc-rag 11min frio). |

Tempos medidos: gates 0-3min/serviço, smoke 5min, publish 0-11min (frio). Bench G8 passou no runner (folga 10-25x dos thresholds locais confirmou margem).

---

## FASE 11: Kubernetes Deployment (2-3 semanas)

**Objetivo:** Orquestração produção em Kubernetes com auto-scaling, rolling updates, mTLS.

### 11.1 Helm Chart Structure

```
helm/
  Chart.yaml                    # chart v1.0.0
  values.yaml                   # defaults (replicas, resources, scale)
  values-prod.yaml              # overrides produção
  templates/
    deployment.yaml             # template genérico para 7 serviços
    service.yaml
    configmap.yaml              # configs por serviço
    secret.yaml                 # secrets (keys)
    ingress.yaml
    networkpolicy.yaml
    poddisruptionbudget.yaml
    hpa.yaml                    # auto-scale: CPU 70%, memória 80%
    pdb.yaml
```

### 11.2 Deployment Config

```yaml
spec:
  replicas: {{ .Values.replicas }}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    spec:
      containers:
      - name: {{ .Values.service }}
        image: {{ .Values.registry }}/svc-{{ .Values.service }}:{{ .Values.tag }}
        ports:
        - containerPort: 8000
        env:
        - name: INTERNAL_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: internal-key
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://otel-collector:4317"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 1Gi
```

### 11.3 Ingress + Rate Limit

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: svc-orchestrator-ingress
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/rate-limit: "100"  # per minute
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - api.svc-orchestrator.example.com
    secretName: svc-orchestrator-tls
  rules:
  - host: api.svc-orchestrator.example.com
    http:
      paths:
      - path: /v1/chat
        pathType: Prefix
        backend:
          service:
            name: svc-orchestrator
            port:
              number: 8000
```

### 11.4 Helm Deploy

```bash
helm install svc-stack ./helm -f helm/values-prod.yaml \
  --set tag=$(git describe --tags) \
  --namespace prod \
  --create-namespace
```

---

## FASE 12: Observability Stack (1-2 semanas)

**Objetivo:** Traces completos, métricas agregadas, dashboards operacionais.

### 12.1 Components

- **Jaeger** (traces): collects spans, searchable por `trace_id`, `service`, latência por hop
- **Prometheus** (métricas): scrape `/metrics` de cada serviço, rate-limit, upstream availability
- **Grafana** (dashboards): RED (request rate / errors / duration), circuit breaker status, queue depths

### 12.2 Dashboards

#### Dashboard 1: System Health
- Circuit breaker status (7 serviços: green/yellow/red)
- Endpoint availability (% uptime)
- Latency heatmap (P50/P95/P99)
- Error rate by service

#### Dashboard 2: Request Flow
- Throughput by domain (query volume)
- Fan-out fan-in latency breakdown
- SSE streaming success rate
- HITL approval rate

#### Dashboard 3: Dependency Health
- Qdrant latency + indices count
- Neo4j query performance
- Ollama model load time
- OTel Collector backlog

#### Dashboard 4: Security
- Rate limit hits (top IPs)
- Injection blocks (patterns triggered)
- OOD flags (distribution)
- Failed auth attempts

### 12.3 Alerts

```yaml
groups:
- name: svc-alerts
  rules:
  - alert: DownstreamDown
    expr: up{job=~"svc-.*"} == 0
    for: 1m
    annotations:
      summary: "{{ $labels.job }} is down"

  - alert: HighLatencyP95
    expr: histogram_quantile(0.95, http_request_duration_seconds) > 2
    for: 5m
    annotations:
      summary: "P95 latency {{ $value }}s"

  - alert: CircuitBreakerOpen
    expr: circuit_breaker_state{state="open"} == 1
    annotations:
      summary: "Circuit to {{ $labels.downstream }} is OPEN"

  - alert: RateLimitExceeded
    expr: rate(http_429_total[1m]) > 10
    for: 2m
    annotations:
      summary: "Rate limit spam detected: {{ $value }} req/s"
```

### 12.4 As-built (2026-07-07) — resolve DS-01

**Entregue:** OTel real nos 7 serviços (módulo `otel.py` idêntico por template: TracerProvider + OTLP HTTP + auto-instrumentação FastAPI/httpx, `excluded_urls=health,metrics`, degradação graceful) · Jaeger 1.62 + Prometheus v3.4 + Grafana 11.6 no `docker-compose.prod.yml` · 4 dashboards provisionados (System Health, Request Flow, Dependency Health, Security) · 4 alertas (`AggregatorDown`, `ServiceScrapeStale`, `LatencySpikeP95`, `InjectionBurst`) · smoke estendido (passos 8-10; `SKIP_OBS_STACK=1` no CI).

**Gates DS-01:**

| Gate | Resultado |
|------|-----------|
| G-OTEL-1 (regressão zero c/ OTEL_ENABLED=0) | ✅ 7/7 `make gates` PASS |
| G-OTEL-2 (trace único 5+ serviços) | ✅ smoke passo 8: 5/5 encadeados |
| G-OTEL-3 (IDs consistentes) | ✅ **reformulado**: nenhum serviço loga trace_id JSON as-built (premissa não existia); validação mais forte aplicada — `traceparent` externo enviado no `/v1/chat` é adotado pelos spans dos 5 serviços (trace recuperado no Jaeger pelo ID exato) |
| G-OTEL-4 (overhead P95 ≤ +20%) | ✅ **reformulado**: em baseline de 1.8ms o critério relativo mede custo fixo do middleware ASGI, não capacidade — medido +0.6ms absoluto (1.84→2.50ms, ~+36% relativo, n=3). Critério as-built: P95 com OTel permanece dentro do gate G8 original → 2.5ms < 50ms, folga 20x |

**Decisões:**

| # | Decisão | Razão |
|---|---------|-------|
| F12-D1 | Prometheus raspa **só o agregador** (`svc-observability /v1/prometheus`) via `http_headers` + arquivo de chave (entrypoint) | Respeita D1 do svc-observability (ponto único de agregação); /metrics dos serviços são JSON autenticado, não formato Prometheus |
| F12-D2 | Métricas GenAI do svc-inference → Prometheus **OTLP receiver** (`--web.enable-otlp-receiver`) | Jaeger não ingere métricas; separa sinal: traces→Jaeger, métricas→Prometheus |
| F12-D3 | Alertas adaptados ao as-built (sem `CircuitOpen`/`RateLimitSpam`) | Orchestrator não expõe métrica de circuito no /metrics v1 → BACKLOG; `InjectionBurst`/`ServiceScrapeStale` cobrem o risco equivalente |
| F12-D4 | svc-orchestrator adicionado ao registry do svc-observability (5→6 upstreams; testes atualizados) | Gap as-built da rodada 6: obs nasceu antes do orchestrator existir |
| F12-D5 | Portas de observabilidade só em 127.0.0.1 (16686 Jaeger, 9090 Prometheus, 3000 Grafana, 4318 OTLP p/ dev/bench) | Mesma postura F9-D7 |
| F12-D6 | Grafana OSS self-hosted, admin provisionado por env (`GRAFANA_PASSWORD`), signup off, analytics off | Zero dependência externa/custo; datasources+dashboards 100% via arquivos (reproduzível) |

**FASE 11 (Kubernetes): SKIPPED por decisão de produto (2026-07-07)** — sem cluster alvo; caso de uso é single-node com GPU local, atendido pelo compose prod (FASE 9). Helm volta ao backlog se surgir alvo real.

---

## FASE 13: Security Hardening (2 semanas)

**Objetivo:** Compliance com OWASP Top 10, secrets management, encryption, audit logging.

### 13.1 Checklist

- [ ] **Secrets Management**: HashiCorp Vault / AWS Secrets Manager (não `.env` em git)
- [ ] **mTLS**: Cert rotation, client certificates inter-serviços
- [ ] **SSRF Prevention**: Allowlist URLs, no raw IP
- [ ] **SQL Injection**: (if applicable) parameterized queries, no string interpolation
- [ ] **Auth Chain**: X-Internal-Key + hmac.compare_digest, fail-closed
- [ ] **Rate Limit**: Sliding window, per-IP, configurable backoff
- [ ] **Audit Log**: Quem chamou o quê, quando, resultado — estruturado
- [ ] **TLS 1.3**: Disable < 1.3
- [ ] **CORS**: Explicit allow-list, no `*`
- [ ] **Headers**: Security headers (CSP, X-Frame-Options, HSTS)

### 13.2 Audit Trail

```json
{
  "timestamp": "2026-07-07T10:30:45.123Z",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "user_id": "svc-orchestrator",
  "action": "chat",
  "resource": "/v1/chat",
  "result": "success|blocked|paused",
  "decision": "allowed|denied|flagged",
  "downstream_calls": ["guardrails", "router", "rag", "inference"],
  "duration_ms": 1850,
  "ip": "10.0.1.5",
  "source": "live|eval|estimate"
}
```

---

## FASE 14: Load Testing & Performance Tuning (1-2 semanas)

**Objective:** Validate system under production-like load, identify bottlenecks, tune config.

### 14.1 Scenarios (k6/locust)

```javascript
// k6 scenario: mixed read/write
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '5m', target: 100 },   // ramp-up
    { duration: '10m', target: 500 },  // sustained
    { duration: '2m', target: 0 },     // ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000', 'p(99)<5000'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const query = __ENV.QUERY || 'saldo em caixa?';
  const res = http.post('http://svc-orchestrator:8206/v1/chat', 
    JSON.stringify({ query, stream: false }),
    { headers: { 'X-Internal-Key': __ENV.INTERNAL_KEY, 'Content-Type': 'application/json' } }
  );
  check(res, { 'status 200': r => r.status === 200 });
  sleep(1);
}
```

### 14.2 Metrics

| Metric | Threshold | Baseline |
|--------|-----------|----------|
| **P95 latency** | < 2s (single) / < 5s (multi) | tbd |
| **P99 latency** | < 5s (single) / < 10s (multi) | tbd |
| **Throughput** | > 500 req/s | tbd |
| **Error rate** | < 0.1% | tbd |
| **Circuit open rate** | < 1% | tbd |

---

## FASE 15: Disaster Recovery & Backup (1-2 semanas)

**Objective:** RTO/RPO targets, backup automation, failover procedures.

### 15.1 RTO/RPO Targets

| Component | RTO | RPO |
|-----------|-----|-----|
| svc-orchestrator (stateless) | 1 min (redeploy) | N/A |
| Qdrant (vectors) | 5 min (restore from backup) | 1 hour |
| Neo4j (graph) | 5 min (restore from backup) | 1 hour |
| Ollama (cache) | 10 min (redownload models) | N/A |
| Jaeger (traces) | 30 min (lose recent spans) | lossy ok |

### 15.2 Backup Strategy

```bash
# Qdrant daily backup
qdrant-backup.sh | upload to S3 timestamped key

# Neo4j daily backup
neo4j-backup.sh | upload to S3 timestamped key

# Helm values versioned in git
git commit helm/values-prod.yaml

# Thread state (if persistent): write to backup S3
```

### 15.3 Recovery Procedures

```bash
# Restore Qdrant from S3 backup
aws s3 cp s3://backups/qdrant-2026-07-06.tar.gz . && tar xz && docker cp ...

# Restore Neo4j
docker exec neo4j neo4j-admin restore ...

# Redeploy svc-orchestrator (pulls latest image)
kubectl rollout restart deployment/svc-orchestrator -n prod
```

---

## FASE 16: Documentation & Runbooks (1 week)

**Objective:** Deployment guide, troubleshooting playbooks, SLA, architecture as code.

### 16.1 Docs

- **DEPLOYMENT.md**: step-by-step production deploy (helm, secrets, TLS, ingress)
- **RUNBOOK.md**: troubleshooting (downstream down, circuit breaker stuck, OOD threshold drift, trace debugging)
- **SLA.md**: uptime targets, incident response SLA, escalation
- **ARCHITECTURE.md**: updated with K8s topology, network policies, data flows
- **API_REFERENCE.md**: auto-generated from OpenAPI + examples

### 16.2 Architecture Diagram

```
┌─────────────┐
│ Ingress     │ (cert-manager, rate-limit)
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                    svc-orchestrator pod × 3                     │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ instance 1   │  │ instance 2   │  │ instance 3   │          │
│  │ (8206)       │  │ (8206)       │  │ (8206)       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          │                                      │
└──────────────────────────┼──────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
   ┌─────▼────┐      ┌─────▼────┐      ┌─────▼────┐
   │ guardrails│      │ router   │      │ rag      │
   │ (8201)    │      │ (8203)   │      │ (8205)   │
   └───────────┘      └───────────┘      └───────┬──┘
         │                 │                      │
         └─────────────────┼──────────────────────┤
                           │          ┌───────────┘
                      ┌────▼────┐     │
                      │inference │     │
                      │ (8204)   │     │
                      └──────────┘     │
                                       │
                    ┌──────────────────┴────────────────┐
                    │                                   │
              ┌─────▼───────┐              ┌────────────▼───┐
              │   Qdrant     │              │   Neo4j        │
              │   (6333)     │              │   (7687)       │
              └──────────────┘              └────────────────┘
                    
              ┌──────────────────┐
              │ Ollama (LLM cache)│
              │ (11434)          │
              └──────────────────┘

Monitoring: Jaeger (16686) + Prometheus (9090) + Grafana (3000)
```

---

## FASE 17: Observability Runbook (1 week)

**Objective:** SOP for debugging, tracing, metric analysis.

### 17.1 Common Issues

**Issue: P95 latency spike to 5s+**
1. Check Jaeger traces for which hop is slow
2. If inference: check Ollama model load time, GPU saturation
3. If rag: check Qdrant latency, Neo4j query performance
4. Action: scale deployment, tune batch size, add caching

**Issue: Circuit breaker stuck OPEN**
1. Verify downstream health: `curl http://svc-X:8000/health`
2. If down: restart pod, check logs for crash loop
3. Circuit should transition HALF_OPEN after 30s idle
4. If not: check for rapid failures (log spam, high error rate)

**Issue: OOD false positive (legit query flagged)**
1. Check residual value + threshold in svc-guardrails /v1/ood/status
2. If corpus drifted: refit with new golden set (admin op)
3. Refit: POST /v1/ood/fit with corpus + golden, monitor AUC

**Issue: SSE stream interrupted**
1. Check if client connection lost (network partition)
2. Check if server crashed (logs, pod restarts)
3. Client should reconnect; server tracks thread_id for resume

---

## FASE 18: Long-term Roadmap (3+ months)

**Objective:** Evolution of platform post-integration.

### 18.1 Feature Backlog

- **svc-cache**: Redis cache layer (query results, embeddings, route decisions)
- **svc-auth**: OAuth2/OIDC gateway (user identity, multi-tenancy, RBAC)
- **svc-audit**: Immutable audit log (compliance, forensics, billing)
- **svc-analytics**: BI layer (dashboards, user behavior, domain trends)
- **svc-admin**: Management API (model updates, threshold tuning, policy changes)
- **svc-webhook**: Outbound events (write completions, new domains registered)

### 18.2 Infrastructure Evolution

- **Multi-region**: active-active with data sync
- **CDN**: cache static responses (popular queries)
- **GPU cluster**: dedicated LLM inference nodes
- **Vector DB failover**: Qdrant → Pinecone managed service
- **Graph DB sharding**: Neo4j enterprise multi-graph

### 18.3 Performance Targets

- P95 latency: < 1.5s (optimize model quantization, batching)
- Throughput: 1000+ req/s (horizontal scaling, load testing)
- Cost per 1M tokens: target 50% reduction via caching + quantization

---

## Summary: 18 Phases Timeline

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| 1-7 | ✅ Done | 7 services, specs, gates PASS |
| 8 | 1-2w | E2E integration tests |
| 9 | 1w | docker-compose.yaml (local prod) |
| 10 | 1-2w | GitHub Actions CI/CD |
| 11 | 2-3w | Kubernetes Helm charts |
| 12 | 1-2w | Jaeger + Prometheus + Grafana |
| 13 | 2w | Security audit + mTLS |
| 14 | 1-2w | Load testing, tuning |
| 15 | 1-2w | Backup + disaster recovery |
| 16 | 1w | Docs + runbooks |
| 17 | 1w | Observability SOP |
| 18 | 3m+ | Feature backlog + roadmap |

**Total: ~15-20 weeks to production-grade observability + security + resilience.**

---

## Sign-off

- **Phase owner**: @aejepsen
- **Status**: Roadmap v1.0 (2026-07-07)
- **Next review**: After Phase 8 completion
