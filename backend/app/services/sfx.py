"""Predlozi okvira za onomatopeje iz maske teksta modela comic-text-detector (ONNX, CPU).

Detektor oblačića ne vidi rukom crtane onomatopeje (SWACK, THUD), ali ih maska piksela teksta
često pokriva. Benchmark Faze 2: 3/5 onomatopeja i 3 lažna predloga na 12 stranica.
"""

import logging
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

from app.services.geometry import Box, area, overlap

INPUT_SIZE = 1024
MASK_THRESHOLD = 0.3
DILATE = 25  # spaja slova onomatopeje u jednu oblast
MIN_AREA_SHARE = 0.005  # manje oblasti su uglavnom mrlje na crtežu
MAX_KNOWN_OVERLAP = 0.3

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _session(model_path: str) -> ort.InferenceSession:
    return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def text_mask(image: Image.Image, model_path: Path) -> np.ndarray:
    """Verovatnoća teksta (0–1) za svaki piksel stranice."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    scale = INPUT_SIZE / max(width, height)
    resized = rgb.resize((round(width * scale), round(height * scale)), Image.Resampling.BILINEAR)
    canvas = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.float32)
    canvas[: resized.height, : resized.width] = np.asarray(resized, dtype=np.float32) / 255.0
    inputs = {"images": canvas.transpose(2, 0, 1)[None]}
    seg = _session(str(model_path)).run(["seg"], inputs)[0][0, 0]
    return cv2.resize(seg[: resized.height, : resized.width], (width, height))


def mask_candidates(mask: np.ndarray, known: list[Box]) -> list[Box]:
    """Velike oblasti maske koje ne pripadaju već pronađenom tekstu ili oblačiću."""
    height, width = mask.shape
    kernel = np.ones((DILATE, DILATE), np.uint8)
    binary = cv2.dilate((mask > MASK_THRESHOLD).astype(np.uint8), kernel)
    count, _, stats, _ = cv2.connectedComponentsWithStats(binary)
    candidates = []
    for x, y, w, h, _ in stats[1:count]:
        box = (float(x), float(y), float(w), float(h))
        if area(box) < MIN_AREA_SHARE * width * height:
            continue
        if all(overlap(box, other) < MAX_KNOWN_OVERLAP for other in known):
            candidates.append(box)
    return candidates


def sfx_candidates(image: Image.Image, known: list[Box], model_path: Path) -> list[Box]:
    if not model_path.exists():
        log.warning("nema modela %s, predlozi za onomatopeje su preskočeni", model_path)
        return []
    return mask_candidates(text_mask(image, model_path), known)
