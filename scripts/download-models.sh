#!/usr/bin/env bash
# Preuzima težine modela u models/ (van git-a) i proverava SHA256.
set -euo pipefail
cd "$(dirname "$0")/.."

download() {  # putanja-u-models url sha256
  local target="models/$1" url="$2" sha="$3"
  if [[ -f "$target" ]] && echo "$sha  $target" | sha256sum -c --quiet 2>/dev/null; then
    echo "već postoji: $target"
    return
  fi
  mkdir -p "$(dirname "$target")"
  echo "preuzimam: $target"
  curl -fsSL --retry 3 -o "$target.part" "$url"
  echo "$sha  $target.part" | sha256sum -c --quiet
  mv "$target.part" "$target"
}

# ogkalu/comic-text-and-bubble-detector (Apache-2.0): oblačić, tekst u oblačiću, tekst van oblačića
HF=https://huggingface.co/ogkalu/comic-text-and-bubble-detector/resolve/main
download comic-text-and-bubble-detector/detector.onnx "$HF/detector.onnx" 065744e91c0594ad8663aa8b870ce3fb27222942eded5a3cc388ce23421bd195
download comic-text-and-bubble-detector/detector_int8.onnx "$HF/detector_int8.onnx" b5022ad46416b6fe4f88b0cc082cfd2ff5b1cfc624088c2f19879485493f5913
download comic-text-and-bubble-detector/detector-v4-s_int8.onnx "$HF/detector-v4-s_int8.onnx" 5fe9e4f576e49d4e7e8b0e029d6d3cdc252abd4694113e1cae120e62c931ea79

# comic-text-detector (dmMaze, ONNX: mayocream/comic-text-detector-onnx, Apache-2.0): blokovi + maska piksela teksta
download comic-text-detector/comic-text-detector.onnx https://huggingface.co/mayocream/comic-text-detector-onnx/resolve/main/comic-text-detector.onnx 1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f

# LaMa za mangu i strip (AnimeMangaInpainting, ONNX sa dinamičkom veličinom: ogkalu/lama-manga-onnx-dynamic,
# Apache-2.0): brisanje teksta preko crteža (onomatopeje, natpisi)
download lama-manga/lama-manga-dynamic.onnx https://huggingface.co/ogkalu/lama-manga-onnx-dynamic/resolve/main/lama-manga-dynamic.onnx de31ffa5ba26916b8ea35319f6c12151ff9654d4261bccf0583a69bb095315f9
