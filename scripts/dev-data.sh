#!/usr/bin/env bash
# Kopija podataka stabilnog okruženja (volume striptrans_data) u razvojno (striptrans-dev_data).
# Baza se kopira preko SQLite backup-a, pa je kopija ispravna i dok stabilno okruženje radi (WAL traži
# da izvor nije montiran samo za čitanje; iz njega se samo čita).
set -euo pipefail
cd "$(dirname "$0")/.."
if ! grep -q '^COMPOSE_FILE=.*docker-compose.dev.yml' .env 2>/dev/null; then
  echo "ovo nije razvojni folder (.env nema COMPOSE_FILE sa docker-compose.dev.yml)" >&2
  exit 1
fi
docker compose stop api worker 2>/dev/null || true
docker run --rm -v striptrans_data:/from -v striptrans-dev_data:/to striptrans-api sh -c '
  find /to -mindepth 1 -delete
  cd /from && find . -mindepth 1 -maxdepth 1 ! -name "striptrans.db*" ! -name backups -exec cp -a {} /to/ \;
  python -c "import sqlite3; s = sqlite3.connect(\"/from/striptrans.db\"); d = sqlite3.connect(\"/to/striptrans.db\"); s.backup(d); d.close()"
  # poslovi iz reda stabilnog okruženja se ovde ne izvršavaju (inače bi se OCR radio dvaput)
  python -c "import sqlite3; d = sqlite3.connect(\"/to/striptrans.db\"); d.execute(\"update jobs set status = \x27cancelled\x27 where status in (\x27queued\x27, \x27running\x27)\"); d.commit()"
  du -sh /to'
docker compose up -d --wait api worker
echo "podaci su kopirani u razvojno okruženje"
