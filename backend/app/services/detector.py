"""Detekcija oblačića i teksta: ogkalu/comic-text-and-bubble-detector (RT-DETR-v2, ONNX)."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.services.geometry import Box, area, intersection, iou

INPUT_SIZE = 640
LABELS = {0: "bubble", 1: "text_bubble", 2: "text_free"}
# slobodan tekst ima više lažnih pogodaka na crtežu, pa traži veću sigurnost
MIN_SCORE = {"bubble": 0.5, "text_bubble": 0.5, "text_free": 0.6}
DUPLICATE_IOU = 0.5
MIN_INSIDE_BUBBLE = 0.5  # deo teksta koji mora biti u oblačiću da bi mu pripadao


@dataclass
class Detection:
    label: str
    score: float
    box: Box


@dataclass
class DetectedBlock:
    kind: str
    box: Box
    bubble: Box | None
    score: float | None


@lru_cache(maxsize=2)
def _session(model_path: str) -> ort.InferenceSession:
    return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def postprocess(
    labels, boxes, scores, width: int, height: int, min_score: dict[str, float] | None = None
) -> list[Detection]:
    """Izlaz modela (okviri u prostoru 640×640) → detekcije u pikselima stranice, bez duplikata."""
    scale_x, scale_y = width / INPUT_SIZE, height / INPUT_SIZE
    detections = []
    for label_id, (x1, y1, x2, y2), score in zip(labels, boxes, scores, strict=True):
        label = LABELS.get(int(label_id))
        if label is None or score < (min_score or MIN_SCORE)[label]:
            continue
        left, top = min(max(x1 * scale_x, 0), width), min(max(y1 * scale_y, 0), height)
        right, bottom = min(max(x2 * scale_x, 0), width), min(max(y2 * scale_y, 0), height)
        if right - left > 1 and bottom - top > 1:
            box = (float(left), float(top), float(right - left), float(bottom - top))
            detections.append(Detection(label, float(score), box))
    kept: list[Detection] = []
    for detection in sorted(detections, key=lambda d: d.score, reverse=True):
        is_text = detection.label != "bubble"
        if not any(
            (other.label != "bubble") == is_text and iou(other.box, detection.box) > DUPLICATE_IOU
            for other in kept
        ):
            kept.append(detection)
    return kept


def run_model(image: Image.Image, model_path: Path) -> tuple:
    """Sirov izlaz modela: (oznake, okviri u prostoru 640×640, skorovi, širina, visina)."""
    rgb = image.convert("RGB")
    resized = rgb.resize((INPUT_SIZE, INPUT_SIZE), Image.Resampling.BILINEAR)
    tensor = (np.asarray(resized, dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]
    sizes = np.array([[INPUT_SIZE, INPUT_SIZE]], dtype=np.int64)
    outputs = _session(str(model_path)).run(None, {"images": tensor, "orig_target_sizes": sizes})
    labels, boxes, scores = (output[0] for output in outputs)
    return labels, boxes, scores, *rgb.size


def detect(image: Image.Image, model_path: Path) -> list[Detection]:
    return postprocess(*run_model(image, model_path))


def text_blocks(detections: list[Detection]) -> list[DetectedBlock]:
    """Tekst u oblačiću postaje govor (uz okvir oblačića), tekst van oblačića narativni okvir."""
    bubbles = [d.box for d in detections if d.label == "bubble"]
    blocks = []
    for detection in detections:
        if detection.label == "bubble":
            continue
        bubble = max(bubbles, key=lambda b: intersection(detection.box, b), default=None)
        if bubble and intersection(detection.box, bubble) < MIN_INSIDE_BUBBLE * area(detection.box):
            bubble = None
        kind = "speech" if detection.label == "text_bubble" else "caption"
        blocks.append(DetectedBlock(kind, detection.box, bubble, detection.score))
    return blocks
