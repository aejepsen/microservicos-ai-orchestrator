# Stack de produção local (docker-compose.prod.yml)
COMPOSE := docker compose -f docker-compose.prod.yml
MODEL   ?= qwen2.5:3b

.PHONY: up down ps logs model smoke-test clean

up:            ## sobe o stack (build + detach)
	$(COMPOSE) up -d --build

down:          ## derruba o stack (mantém volumes)
	$(COMPOSE) down

ps:            ## status dos serviços
	$(COMPOSE) ps

logs:          ## logs agregados (follow)
	$(COMPOSE) logs -f --tail=100

model:         ## baixa o modelo no volume do Ollama
	$(COMPOSE) exec ollama ollama pull $(MODEL)

smoke-test:    ## valida o stack ponta a ponta
	./scripts/smoke.sh

loadtest:      ## F14: baseline de carga (plano de controle + chat GPU)
	svc-orchestrator/.venv/bin/python scripts/loadtest.py --scenario light --concurrency 20 --requests 1000
	svc-orchestrator/.venv/bin/python scripts/loadtest.py --scenario chat  --concurrency 1  --requests 6

backup:        ## F15: snapshot do Qdrant p/ ./backups (RETAIN=7)
	./scripts/backup.sh

restore:       ## F15: restaura o backup mais recente (ou: make restore DIR=backups/<ts>)
	./scripts/restore.sh $(DIR)

dr-test:       ## F15: teste de disaster recovery ponta a ponta (canary)
	./scripts/dr_test.sh

clean:         ## derruba o stack E APAGA volumes (qdrant + ollama)
	$(COMPOSE) down -v
