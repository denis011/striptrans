"""NOTICE za javnu verziju: licence paketa backenda (iz instaliranih paketa), fontova i modela.

Radi u `api` kontejneru; deo za frontend dodaje `scripts/notice-frontend.cjs`. Paketi sa GPL/AGPL licencom
se prijavljuju kao greška, osim onih koje javna verzija izostavlja.

  docker compose run --rm --no-deps -v "$PWD":/repo api python /repo/scripts/notice.py > backend.md
"""

import importlib.metadata as metadata
import re
import sys
from pathlib import Path

OMITTED = {"potracer"}  # samo alati za fontove, van javne verzije
COPYLEFT = re.compile(r"\bA?GPL|General Public License", re.IGNORECASE)
LESSER = re.compile(r"LGPL|Lesser", re.IGNORECASE)

MODELS = [
    ("comic-text-and-bubble-detector (ogkalu)", "Apache-2.0", "detekcija oblačića i teksta"),
    (
        "comic-text-detector (ONNX: mayocream)",
        "ONNX označen Apache-2.0; izvorni projekat dmMaze/comic-text-detector je GPL-3.0",
        "maska teksta, predlozi onomatopeja",
    ),
    (
        "lama-manga-onnx-dynamic (ogkalu)",
        "ONNX označen Apache-2.0; izvor dmMaze/AnimeMangaInpainting bez navedene licence",
        "brisanje teksta preko crteža",
    ),
    ("Qwen2.5-VL-7B-Instruct (Alibaba, GGUF ggml-org)", "Apache-2.0", "OCR"),
    ("llama.cpp / llama-server", "MIT", "pokretanje OCR modela"),
]


def license_of(dist: metadata.Distribution) -> str:
    data = dist.metadata
    text = data.get("License-Expression") or data.get("License") or ""
    text = text.splitlines()[0].strip() if text.strip() else ""
    classifiers = [
        c.split("::")[-1].strip() for c in data.get_all("Classifier") or [] if c.startswith("License")
    ]
    if not text or text.upper() == "UNKNOWN" or len(text) > 60:
        text = ", ".join(classifiers) or text or "?"
    return text


def main() -> None:
    constraints = Path("/app/constraints.txt").read_text().splitlines()
    names = [line.split("==")[0] for line in constraints if "==" in line]
    rows, problems = [], []
    for name in sorted(names, key=str.lower):
        if name in OMITTED:
            continue
        dist = metadata.distribution(name)
        text = license_of(dist)
        if COPYLEFT.search(text) and not LESSER.search(text):
            problems.append(f"{name}: {text}")
        rows.append(f"| {name} | {dist.version} | {text} |")
    if problems:
        print("GPL/AGPL paketi:", *problems, sep="\n  ", file=sys.stderr)
        sys.exit(1)
    fonts = sorted(p.stem.split("-")[0] for p in Path("/app/app/fonts/licenses").glob("*.txt"))
    print("## Python paketi (backend)\n\n| Paket | Verzija | Licenca |\n|---|---|---|")
    print("\n".join(rows))
    print("\n## Fontovi u `backend/app/fonts`\n")
    print(f"SIL Open Font License 1.1 (tekst u `backend/app/fonts/licenses/`): {', '.join(fonts)}.")
    print("\n## Modeli (preuzimaju se pri instalaciji, nisu u repozitorijumu)\n")
    print("| Model | Licenca | Namena |\n|---|---|---|")
    print("\n".join(f"| {name} | {text} | {use} |" for name, text, use in MODELS))


if __name__ == "__main__":
    main()
