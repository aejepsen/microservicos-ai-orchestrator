# GUIA DE RETOMADA — Do Que Foi Pausado (Fase SDD → Fase 8+)

**Data**: 2026-07-07
**Status anterior**: SDD rodadas 1-7 finalizadas (G1-G8 PASS)
**Status atual**: ✅ FASE 8 (E2E) CONCLUÍDA — 22 cenários PASS. Próxima: FASE 9 (compose de produção)
**Owner**: @aejepsen

---

## O QUE ESTAVA SENDO FEITO (antes da pausa)

### Contexto
O programa **SDD (Spec-Driven Development)** completou a **fase de especificação + construção** de 7 microsserviços através de:

1. **Template elaborado** (`SDD/SPEC_TEMPLATE.md`)
2. **7 especificações detalhadas** (uma por serviço)
3. **Loop de agentes autônomos** construindo cada serviço contra sua spec
4. **8 Gates de aceitação** (G1-G8) por serviço, validando qualidade

**Todas as 7 rodadas passaram 100% dos gates na 1ª tentativa.**

### Onde parou

**Entrega final (2026-07-06, ~22:30)**:
- svc-orchestrator (rodada 7): Todos os 8 gates PASS
- Todas as imagens Docker construídas e testadas localmente
- Repositórios individuais (`svc-*/`) prontos com SPEC congelada
- Lições aprendidas institucionalizadas em template

**O que NÃO foi feito**:
- ✅ Testes E2E integrando os 7 serviços (FASE 8 — `tests/e2e/`, 22 PASS)
- ❌ Docker Compose para produção
- ❌ CI/CD pipeline GitHub Actions
- ❌ Kubernetes manifests
- ❌ Observability stack (Jaeger, Prometheus, Grafana)
- ❌ Load testing
- ❌ Security audit produção
- ❌ Deployment em produção

---

## COMO RETOMAR (Passo-a-passo)

### PASSO 1: Validar Estado Atual

```bash
cd /home/aejepsen/Documentos/projeto-portifolio/microservicos-ai-orchestrator

# Verificar imagens Docker construídas
docker images | grep msvc-e2e

# Esperado:
# msvc-e2e-svc-evals:latest          247MB
# msvc-e2e-svc-guardrails:latest     247MB
# msvc-e2e-svc-inference:latest      247MB
# msvc-e2e-svc-observability:latest  247MB
# msvc-e2e-svc-orchestrator:latest   247MB
# msvc-e2e-svc-rag:latest            247MB
# msvc-e2e-svc-router:latest         247MB

# Verificar G1-G8 de cada serviço (rápido)
for dir in svc-*/; do
  echo "=== $dir ==="
  cd "$dir"
  make gates 2>&1 | grep -E "^\[G[0-9]\]" | tail -1
  cd ..
done
```

### PASSO 2: Retomar do Documento Roadmap

**Arquivo**: `SDD/NEXT_PHASES.md` (criado 2026-07-07)

Este documento detalha **18 fases** (8-25) com:
- Especificações completas de cada fase
- Acceptance criteria
- Dependências entre fases
- Estimativas de tempo
- Comandos de início/verificação

### PASSO 3: ~~Iniciar FASE 8 (E2E Integration Testing)~~ ✅ CONCLUÍDA — ver NEXT_PHASES.md §8.4

**Objetivo**: Validar que os 7 serviços funcionam juntos, com circuit breakers, traces, HITL, SSE.

```bash
# 1. Crie diretório de testes E2E
mkdir -p tests/e2e

# 2. Escreva a suite (ver NEXT_PHASES.md §8.1 para template completo)
# Arquivos:
#   tests/e2e/test_full_flow.py         # chat completo: guard → route → fan-out → fan-in
#   tests/e2e/test_resilience.py        # circuit breaker, downstream restart
#   tests/e2e/test_sse_streaming.py     # SSE eventos in-order
#   tests/e2e/test_hitl_approval.py     # pausa-retoma escrita
#   tests/e2e/test_distributed_trace.py # traceparent W3C
#   tests/e2e/conftest.py               # fixture: docker-compose up, await /health

# 3. Levante todos os 7 serviços
docker-compose up -d

# 4. Aguarde healthchecks OK (pode usar script fixture)
while ! curl -s http://svc-orchestrator:8206/health | jq .status | grep -q healthy; do sleep 1; done

# 5. Rode os testes
pytest tests/e2e/ -v

# Esperado: 10 cenários × pytest → 100% pass
```

### PASSO 4: Docker Compose para Produção (FASE 9)

**Entrega**: `docker-compose.yaml` na raiz do projeto com:
- 7 serviços + infra (Qdrant, Neo4j, Ollama, Jaeger)
- Networks isoladas
- Volumes para persistência
- Health checks

```bash
# Arquivo target: ./docker-compose.yaml

# Structure esperada:
services:
  svc-orchestrator:
    image: msvc-e2e-svc-orchestrator:latest
    ports: ["8206:8000"]
    depends_on:
      - svc-guardrails
      - svc-router
      - svc-inference
      - svc-rag
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  svc-guardrails: ...
  svc-router: ...
  svc-inference: ...
  svc-rag: ...
  svc-observability: ...
  svc-evals: ...

  # Infra
  ollama:
    image: ollama/ollama:latest
  qdrant:
    image: qdrant/qdrant:latest
  neo4j:
    image: neo4j:latest
  jaeger:
    image: jaegertracing/all-in-one:latest

volumes:
  qdrant_storage:
  neo4j_data:
  ollama_data:
```

### PASSO 5: CI/CD Pipeline (FASE 10)

**Entrega**: `.github/workflows/ci-multi.yml`

```yaml
# Estrutura esperada:
name: SDD Multi-Service Pipeline
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [guardrails, router, rag, inference, orchestrator, observability, evals]
    steps: ...

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [...]
    steps:
      - run: cd svc-${{ matrix.service }} && make gates

  build:
    needs: [lint, test]
    strategy:
      matrix:
        service: [...]
    steps:
      - run: docker build -t $ECR/svc-${{ matrix.service }}:${{ github.sha }} .
      - run: docker push ...

  e2e:
    needs: build
    steps:
      - run: docker-compose pull && docker-compose up -d
      - run: pytest tests/e2e/ -v
```

---

## RESOURCES DISPONÍVEIS

### Documentos já criados

| Arquivo | Criado | Propósito |
|---------|--------|----------|
| `SDD/NEXT_PHASES.md` | 2026-07-07 | Roadmap 18 fases com specs completas |
| `SDD/STATUS_EXECUTIVO.md` | 2026-07-07 | Resumo do programa SDD + próximas fases |
| Este arquivo | 2026-07-07 | Guia de retomada |

### Código-base pronto

| Recurso | Status | Local |
|---------|--------|-------|
| 7 serviços scaffolded | ✅ | `svc-*/` |
| Specs congeladas | ✅ | `svc-*/SPEC.md` + `SDD/specs/` |
| Unit + contract tests | ✅ | `svc-*/tests/` (417 testes total) |
| Docker images | ✅ | Local (7× 247MB) |
| OpenAPI contracts | ✅ | `svc-*/api/openapi.yaml` |

### Checklist de retomada

- [ ] Ler `SDD/NEXT_PHASES.md` (entender timeline + fases)
- [ ] Verificar imagens Docker: `docker images | grep msvc-e2e`
- [ ] Verificar G1-G8 de cada serviço: `make gates` em cada `svc-*/`
- [x] Criar `tests/e2e/` (feito — 6 arquivos + conftest)
- [x] Levantar `docker compose -f docker-compose.e2e.yml up -d --build`
- [x] Validar `/health` de todos (fixture `stack` faz isso)
- [x] Rodar E2E: `python3 -m pytest tests/e2e` → 22 PASS total
- [x] **Fase 8 completa** ✅ — seguir para FASE 9 (NEXT_PHASES.md §9)

---

## CONTEXTO TÉCNICO (referência rápida)

### Fluxo da orquestração

```
query
  ↓
guardrails (svc-guardrails) → /v1/analyze
  ↓ [allow/flag/block]
router (svc-router) → /v1/route (domínios)
  ↓ [domains: ["financas", "rh"]]
fan-out (paralelo):
  ├─ domain=financas → rag + inference
  ├─ domain=rh → rag + inference
  └─ ...
  ↓
HITL check:
  write_intent? + !allow_write? → PAUSA (event: paused)
  else → continue
  ↓
fan-in (sintese):
  svc-inference → /v1/chat/completions (multi-domínio)
  ↓ [final: "...síntese..."]
  ↓
SSE event: final → client

Observabilidade:
  traceparent W3C propagado em todos os hops → Jaeger
  logs JSON com trace_id → svc-observability
```

### Arquitetura de dependências

```
Serviço         Dependências de runtime    Gate crítico
─────────────────────────────────────────────────────
orchestrator    guardrails, router, rag,  G2 (fluxo), G3 (HITL),
                inference                 G4 (SSE + resilência)

router          inference (LLM layer)     G2 (acurácia), G4 (guards)
rag             (nenhuma)                 G2 (recall), G4 (chunking)
inference       (LLM local: Ollama)       G2 (compat OpenAI)
guardrails      (nenhuma, determinístico) G2 (injection FN=0), G4 (OOD)
evals           todos (golden runs)       G2 (motor de gates)
observability   todos (coleta OTLP)       G2 (agregação)
```

### Configurações críticas

**`INTERNAL_KEY`**: Secret compartilhado entre serviços
- Exemplo: `INTERNAL_KEY=your-secret-key-change-in-prod`
- Usar em dev: `ALLOW_OPEN_ACCESS=1` (NUNCA em prod)

**Variáveis por serviço** (ver `svc-*/SPEC.md` §7):
- `OTEL_ENABLED`: ativa tracing (0=off, 1=on)
- `LOG_LEVEL`: INFO|DEBUG|WARNING
- `OOD_ACTION`: flag|block (guardrails)
- `HITL_ENABLED`: 0|1 (orchestrator)

---

## PRÓXIMAS CALLS

### Semana 1 (agora)
1. **Ler roadmap**: `SDD/NEXT_PHASES.md`
2. **E2E tests**: Escrever 10 cenários (fase 8)
3. **Docker Compose**: Prod-ready compose.yaml (fase 9)

### Semana 2
4. **CI/CD**: GitHub Actions workflow (fase 10)
5. **Kubernetes**: Helm charts esboço (fase 11)

### Semana 3+
6. **Observability**: Jaeger + Prometheus + Grafana (fase 12)
7. **Security**: Audit + mTLS + secrets (fase 13)
8. **Load testing**: k6 scenarios + tuning (fase 14)

---

## TROUBLESHOOTING RÁPIDO

**P: Gates estão passando mas compose falha?**
A: Gates rodam com FakeClients (offline); compose testa com downstreams reais. Verifique:
- Portas em conflito? `lsof -i :8206` etc
- Network name: `docker network ls | grep msvc`
- Health: `curl http://svc-orchestrator:8206/health`

**P: E2E testes falham com timeout?**
A: Aumentar `depends_on.condition` para `service_healthy`. Ou criar wait-script em `conftest.py`:
```python
@pytest.fixture(scope="session", autouse=True)
def wait_for_services():
    for svc in ["orchestrator", "guardrails", "router", "inference", "rag"]:
        url = f"http://svc-{svc}:8000/health"
        for _ in range(30):
            try:
                if requests.get(url).json()["status"] == "healthy":
                    break
            except: pass
            sleep(1)
```

**P: Jaeger traces não aparecem?**
A: Verificar:
- `OTEL_ENABLED=1` em todos os serviços
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318` configurado
- Jaeger rodando: `curl http://localhost:16686/api/services`

**P: Qdrant retorna 502?**
A: Qdrant precisa de volume persistent. Checar:
- Volume criado: `docker volume ls | grep qdrant`
- Permissões: `docker exec qdrant ls -la /qdrant/storage`

---

## SIGN-OFF & CONTATO

**Programa SDD**: ✅ Concluído (7/7 rodadas, 100% gates PASS)
**Próxima fase**: FASE 9 — docker-compose de produção (FASE 8 concluída em 2026-07-07)
**Owner**: @aejepsen (Abacus AI CLI)
**Última atualização**: 2026-07-07
**Status**: Ready to resume

---

## APÊNDICE: Checklist por Fase

### Fase 8: E2E Integration Testing ✅ CONCLUÍDA
- [x] `tests/e2e/conftest.py` com fixtures (skip-if-down, seed RAG, warm-up LLM)
- [x] 6 arquivos de teste (full flow, HITL, SSE, trace, resiliência, matriz)
- [x] Stack: `docker compose -f docker-compose.e2e.yml up -d --build`
- [x] Run: `python3 -m pytest tests/e2e` → 20 passed, 3 skipped
- [x] Destrutivos: `E2E_RESILIENCE=1 python3 -m pytest tests/e2e/test_resilience.py` → 2 passed
- [x] Bug real corrigido: QdrantStore point-id (svc-rag/DECISIONS.md D8)

### Fase 9: Docker Compose Produção
- [ ] Create `./docker-compose.yaml` na raiz
- [ ] Adicione volumes, networks, healthchecks
- [ ] Test: `docker-compose up -d && sleep 15 && make smoke-test`
- [ ] Fase 9 ✅

### Fase 10: GitHub Actions
- [ ] Create `.github/workflows/ci-multi.yml`
- [ ] Configurar matriz (7 serviços)
- [ ] Adicionar secrets: INTERNAL_KEY, ECR credentials
- [ ] Testar localmente: `act push`
- [ ] Fase 10 ✅

**Continue com próximas fases seguindo `SDD/NEXT_PHASES.md` como referência.**
