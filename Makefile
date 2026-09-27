DC := docker compose
UIDGID := $(shell id -u):$(shell id -g)

.PHONY: up down logs models llm-models llm notice public-release test test-backend test-frontend test-integration test-e2e lint format dev-setup dev-data

up: llm
	$(DC) up -d --build --renew-anon-volumes --wait

down:
	$(DC) down

logs:
	$(DC) logs -f

models:
	@scripts/download-models.sh

llm:  ## pokreni llama-server (OCR) na Windows hostu ako ne radi
	@scripts/ensure-llama-server.sh

llm-models:  ## preuzmi OCR model za llama-server (GGUF, ~6 GB)
	@scripts/download-llm.sh

test: test-backend test-frontend

test-backend:
	$(DC) run --rm --no-deps api pytest

test-integration:
	$(DC) run --rm --no-deps api pytest -m integration -v

test-frontend:
	$(DC) run --rm --no-deps frontend npm test

lint:
	$(DC) run --rm --no-deps api sh -c "ruff check . && ruff format --check ."
	$(DC) run --rm --no-deps frontend sh -c "npm run lint && npm run typecheck"

format:
	$(DC) run --rm --no-deps --user $(UIDGID) api sh -c "ruff format . && ruff check --fix ."

test-e2e:  ## E2E: uvoz → čišćenje → izvoz (radi protiv pokrenute aplikacije)
	docker compose --profile e2e run --rm --build e2e

dev-setup:  ## razvojno okruženje u ../striptrans-dev (portovi 5174/8001, kopija podataka); jednom, iz stabilnog foldera
	@scripts/dev-setup.sh

dev-data:  ## osveži kopiju podataka u razvojnom okruženju; pokreće se u razvojnom folderu
	@scripts/dev-data.sh

notice:  ## public/NOTICE.md: licence paketa, fontova i modela (javna verzija)
	@{ printf '# NOTICE\n\nStripTrans koristi sledeće delove drugih autora, pod njihovim licencama.\nStripTrans uses the following third-party components under their own licenses.\n\n'; \
	  $(DC) run --rm --no-deps -v "$$PWD":/repo api python /repo/scripts/notice.py && echo && \
	  $(DC) run --rm --no-deps -v "$$PWD":/repo frontend node /repo/scripts/notice-frontend.cjs; } > public/NOTICE.md.tmp 2>/dev/null \
	  && mv public/NOTICE.md.tmp public/NOTICE.md && echo "public/NOTICE.md" || { rm -f public/NOTICE.md.tmp; exit 1; }

public-release:  ## čista javna kopija u ../striptrans-public (bez slanja na GitHub)
	@scripts/public-release.sh
