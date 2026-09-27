"""Brisanje teksta preko crteža (Faza 4d): onomatopeje i natpisi se brišu LaMa modelom.

Model: big-lama (advimman/lama, Apache-2.0; ONNX Carve/LaMa-ONNX), CPU, ulaz 512×512: isečak sa
okolinom se svede na kvadrat 512 i vrati. U slepom poređenju bolji od ranijeg modela za mangu.
Maska detektora teksta ne vidi četkom crtane onomatopeje (THUD) ni slova na teksturisanoj tabli,
pa se dopunjuje debelim potezima „mastila" u okviru bloka (crno na belom ili belo na crnom).
"""

import logging
import re
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from app.services.geometry import Box

INK_DARK = 140  # tamnije od ovoga je mastilo (uključuje i sive ivice slova)
INK_LIGHT = 150  # svetlije od ovoga su bela slova na tamnoj pozadini
DARK_BACKGROUND = 110  # prosečna siva okvira ispod ovoga: bela slova na crnom
GROW = 0.08  # okvir bloka ume da ne pokrije celo slovo (poslednje F u SHERIFF)
STROKE = 0.05  # debljina poteza slova onomatopeje u odnosu na manju stranu okvira
MIN_PART = 0.003  # manji delovi mastila su šrafura, ne slova
DILATE = 11
PROB = 0.2
CONTEXT = 0.4  # koliko okoline oko okvira model vidi
MAX_SIDE = 1024  # veći isečci se smanjuju zbog brzine

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _session(model_path: str) -> ort.InferenceSession:
    return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def model_path(models_dir: str) -> Path:
    return Path(models_dir, "big-lama", "big-lama-fp32.onnx")


def normalized(text: str) -> str:
    return re.sub(r"[^A-ZČĆŽŠĐ0-9]", "", text.upper())


def needs_inpaint(kind: str, text: str, translation: str) -> bool:
    """Natpis, naslov ili onomatopeja se briše samo ako ima prevod drugačiji od originala.

    Blok bez originalnog teksta je slobodan tekst (korisnik ga je dodao preko crteža): ispod njega
    nema šta da se briše, a maska debelih poteza bi obrisala sam crtež.
    """
    return (
        kind in ("sfx", "other", "title")
        and bool(text.strip())
        and bool(translation.strip())
        and (normalized(translation) != normalized(text))
    )


def artwork_mask(gray: np.ndarray, probability: np.ndarray, box: Box, kind: str) -> np.ndarray:
    """Maska slova onomatopeje ili natpisa: detektor teksta + debeli potezi mastila u okviru."""
    height, width = gray.shape
    x, y, w, h = box
    x0, y0 = max(int(x - w * GROW), 0), max(int(y - h * GROW), 0)
    x1, y1 = min(int(x + w * (1 + GROW)), width), min(int(y + h * (1 + GROW)), height)
    region = gray[y0:y1, x0:x1]
    inner = gray[int(y) : int(y + h), int(x) : int(x + w)]
    light_letters = inner.size > 0 and inner.mean() < DARK_BACKGROUND
    ink = (region > INK_LIGHT) if light_letters else (region < INK_DARK)
    size = max(3, round(STROKE * min(w, h))) if kind == "sfx" else 2
    thick = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, np.ones((size, size), np.uint8))
    count, labels, stats, centers = cv2.connectedComponentsWithStats(thick)
    letters = np.zeros_like(thick)
    for i in range(1, count):
        cx, cy = centers[i][0] + x0, centers[i][1] + y0
        inside = x <= cx <= x + w and y <= cy <= y + h  # crtež sa strane ne ulazi u masku
        if inside and stats[i, cv2.CC_STAT_AREA] >= MIN_PART * w * h:
            letters[labels == i] = 1
    detected = (probability[y0:y1, x0:x1] > PROB).astype(np.uint8)
    mask = np.zeros((height, width), np.uint8)
    mask[y0:y1, x0:x1] = letters | detected
    return cv2.dilate(mask, np.ones((DILATE, DILATE), np.uint8)).astype(bool)


def text_angle(mask: np.ndarray) -> float:
    """Nagib natpisa u stepenima (za slaganje prevoda pod istim uglom); 0 ako se ne vidi."""
    points = np.column_stack(np.nonzero(mask)[::-1]).astype(np.float32)
    if len(points) < 20:
        return 0.0
    (_, _), (w, h), angle = cv2.minAreaRect(points)
    if w < h:  # duža strana pravougaonika je smer teksta
        angle -= 90
    angle = (angle + 90) % 180 - 90
    return float(round(angle, 1)) if abs(angle) <= 45 else 0.0


SIZE = 512  # big-lama radi na kvadratu ove veličine


def inpaint(image: np.ndarray, mask: np.ndarray, models_dir: str) -> np.ndarray:
    """Popuni masku (bool) crtežom; menja samo piksele pod maskom. `image` je RGB uint8."""
    path = model_path(models_dir)
    if not mask.any():
        return image
    if not path.exists():
        log.warning("LaMa model ne postoji (%s): pokreni scripts/download-models.sh", path)
        return image
    ys, xs = np.nonzero(mask)
    left, top, right, bottom = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    margin = int(max(right - left, bottom - top) * CONTEXT) + 16
    height, width = mask.shape
    x0, y0 = max(left - margin, 0), max(top - margin, 0)
    x1, y1 = min(right + margin, width), min(bottom + margin, height)
    crop, hole = image[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    rows, cols = hole.shape
    side = max(rows, cols)
    square = np.pad(crop, ((0, side - rows), (0, side - cols), (0, 0)), mode="reflect")
    square_hole = np.pad(hole, ((0, side - rows), (0, side - cols))).astype(np.uint8)
    small = cv2.resize(square, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    small_hole = cv2.resize(square_hole, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST)
    small_hole = cv2.dilate(small_hole, np.ones((3, 3), np.uint8)).astype(np.float32)
    inputs = {"image": small.transpose(2, 0, 1)[None], "mask": small_hole[None, None]}
    output = _session(str(path)).run(None, inputs)[0][0].transpose(1, 2, 0)  # 0–255
    filled = cv2.resize(
        np.clip(output, 0, 255).astype(np.uint8), (side, side), interpolation=cv2.INTER_CUBIC
    )
    result = image.copy()
    result[y0:y1, x0:x1][hole] = filled[:rows, :cols][hole]
    return result
