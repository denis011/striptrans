#!/usr/bin/env bash
# Preuzima OCR model za llama-server (Qwen2.5-VL 7B, GGUF) u LLAMA_SERVER_DIR\models na Windows-u.
set -euo pipefail
cd "$(dirname "$0")/.."

DIR="$(grep -E '^LLAMA_SERVER_DIR=' .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
MODELS="$(wslpath -u "${DIR:-C:\\llm-bench}")/models"
HF=https://huggingface.co/ggml-org/Qwen2.5-VL-7B-Instruct-GGUF/resolve/main

download() {  # ime sha256
  local target="$MODELS/$1" sha="$2"
  if [[ -f "$target" ]] && echo "$sha  $target" | sha256sum -c --quiet 2>/dev/null; then
    echo "već postoji: $1"
    return
  fi
  mkdir -p "$MODELS"
  echo "preuzimam: $1"
  curl -fL --retry 3 -o "$target.part" "$HF/$1"
  echo "$sha  $target.part" | sha256sum -c --quiet
  mv "$target.part" "$target"
}

download Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf 9258bf05b12686d097ff3b6b18d968ab393649780aa2b3cd67fec43d50554392
download mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf c24a7f5fcfc68286f0a217023b6738e73bea4f11787a43e8238d4bb1b8604cde
