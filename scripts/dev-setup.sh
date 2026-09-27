#!/usr/bin/env bash
# Razvojno okruženje: git worktree u ../striptrans-dev, njegov .env i kopija podataka.
# Pokreće se jednom, iz stabilnog foldera. Grane se posle menjaju u razvojnom folderu (git switch).
set -euo pipefail
cd "$(dirname "$0")/.."
target=../striptrans-dev
if [[ ! -d $target ]]; then
  git worktree add --detach "$target" main
fi
# .env razvojnog foldera: isti ključevi kao stabilni, uz izbor compose fajlova
{
  grep -v '^COMPOSE_FILE=' .env 2>/dev/null || true
  echo 'COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml'
} > "$target/.env"
cd "$target"
docker compose up -d --build --wait
scripts/dev-data.sh
echo "razvojno okruženje: http://localhost:5174 (API http://localhost:8001)"
