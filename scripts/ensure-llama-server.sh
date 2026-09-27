#!/usr/bin/env bash
# Proverava da li OCR server radi na Windows hostu i pokreće ga ako ne radi: llama-server (podrazumevano)
# ili, uz OCR_SERVER=ollama u .env, Ollama (tada se llama-server gasi, a Ollama se ne dira ako radi).
# Ollama se pre toga gasi: dva servera sa učitanim modelom ne staju u 16 GB VRAM-a.
# Podešavanja se čitaju iz .env: LLAMA_SERVER_DIR (podrazumevano C:\llm-bench) i LLAMA_SERVER_PORT.
set -euo pipefail
cd "$(dirname "$0")/.."

env_value() {  # ime podrazumevano
  local value
  value="$(grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
  echo "${value:-$2}"
}

DIR="$(env_value LLAMA_SERVER_DIR 'C:\llm-bench')"
PORT="$(env_value LLAMA_SERVER_PORT 8081)"
SERVER="$(env_value OCR_SERVER auto)"
EXE="$DIR\\vulkan\\llama-server.exe"
MODEL="$DIR\\models\\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
MMPROJ="$DIR\\models\\mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf"
LOG="$DIR\\llama-server.log"
# merenje docs/benchmarks/ocr-llamaserver.md: bez flash attention, slika 1024–1280 tokena kao u Ollami
# (bez gornje granice ogroman blok, npr. ceo stubac teksta, ide minutima)
ARGS="-m \"$MODEL\" --mmproj \"$MMPROJ\" --host 0.0.0.0 --port $PORT -ngl 99 -c 8192 -np 1 -fa off --cache-ram 0 --image-min-tokens 1024 --image-max-tokens 1280"

# PowerShell bez ulaza, sa rokom: Start-Process ume da zadrži poziv otvorenim
pwsh() { timeout 60 powershell.exe -NoProfile -NonInteractive -Command "$1" < /dev/null | tr -d '\r'; }

health() {  # „ok", „loading" (model se učitava) ili prazno (server ne radi)
  pwsh "try { (Invoke-RestMethod -TimeoutSec 2 http://127.0.0.1:$PORT/health).status } catch { if (\$_.Exception.Response.StatusCode.value__ -eq 503) { 'loading' } }" || true
}

wait_ready() {
  for _ in $(seq 1 90); do
    if [[ "$(health)" == "ok" ]]; then
      echo "llama-server radi (port $PORT)."
      return 0
    fi
    sleep 2
  done
  echo "llama-server nije spreman ni posle 3 min; log: $LOG" >&2
  return 1
}

installed() { [[ -f "$(wslpath -u "$1")" ]]; }
LOCALAPPDATA_WIN="$(timeout 20 powershell.exe -NoProfile -NonInteractive -Command '$env:LOCALAPPDATA' < /dev/null | tr -d '\r')"
OLLAMA_EXE="$LOCALAPPDATA_WIN\\Programs\\Ollama\\ollama.exe"
if [[ "$SERVER" == "auto" ]]; then
  # prednost ima llama-server (brži); Ollama ako llama-server nije instaliran
  if installed "$EXE" && installed "$MODEL" && installed "$MMPROJ"; then
    SERVER=llama-server
  elif installed "$OLLAMA_EXE"; then
    SERVER=ollama
  else
    echo "Nije instaliran ni llama-server ($EXE) ni Ollama — vidi docs/UPUTSTVO.md." >&2
    exit 1
  fi
  echo "OCR server: $SERVER (automatski izbor)"
fi
if [[ "$SERVER" == "ollama" ]]; then
  ollama_version() {
    pwsh "try { (Invoke-RestMethod -TimeoutSec 2 http://127.0.0.1:11434/api/version).version } catch { }" || true
  }
  pwsh "Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force" >/dev/null || true
  version="$(ollama_version)"
  if [[ -z "$version" ]]; then
    echo "Ollama ne radi, pokrećem je..."
    timeout 60 powershell.exe -NoProfile -NonInteractive -Command \
      "Start-Process \"\$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe\"" < /dev/null > /dev/null 2>&1 || true
    for _ in $(seq 1 30); do
      version="$(ollama_version)"
      [[ -n "$version" ]] && break
      sleep 1
    done
  fi
  if [[ -z "$version" ]]; then
    echo "Ollama se nije pokrenula za 30 s." >&2
    exit 1
  fi
  echo "Ollama radi (v$version)."
  exit 0
fi

state="$(health)"
if [[ "$state" == "ok" ]]; then
  echo "llama-server radi (port $PORT)."
  exit 0
fi
if [[ "$state" == "loading" ]]; then
  echo "llama-server učitava model..."
  wait_ready
  exit
fi

if [[ ! -f "$(wslpath -u "$EXE")" ]]; then
  echo "Nema $EXE — vidi docs/UPUTSTVO.md (instalacija llama-servera)." >&2
  exit 1
fi
if [[ ! -f "$(wslpath -u "$MODEL")" || ! -f "$(wslpath -u "$MMPROJ")" ]]; then
  echo "Nema modela u $DIR\\models — pokreni: make llm-models" >&2
  exit 1
fi

echo "Gasim Ollamu (ako radi) i pokrećem llama-server..."
pwsh "Get-Process 'ollama app','ollama' -ErrorAction SilentlyContinue | Stop-Process -Force" >/dev/null || true
# izlaz ide u /dev/null, ne u cev: server nasleđuje ručke i cev se ne bi zatvorila
timeout 60 powershell.exe -NoProfile -NonInteractive -Command \
  "Start-Process -FilePath '$EXE' -ArgumentList '$ARGS' -RedirectStandardError '$LOG' -WindowStyle Hidden" \
  < /dev/null > /dev/null 2>&1 || true
wait_ready
