"""Naglasak iz originala: podebljane reči i nagib slova po debljini i nagibu poteza.

Isečak bloka se pretvori u masku slova, podeli na redove (vodoravna projekcija) i delove
reda (razmaci veći od razmaka između slova). Za blok i za svaki deo reda se meri debljina
poteza u odnosu na visinu slova i nagib slova. Povik je ceo blok deblji i ukošen; pojedine
naglašene reči se nađu po delovima reda i preslikaju na tekst po položaju u redu.
Naracija (pravougaoni okvir) se ne naglašava.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from app.models import TextBlock

MIN_LINE_HEIGHT = 0.4  # red niži od ovoliko medijane redova je ostatak (tačka, ivica oblačića)
WORD_GAP = 0.45  # razmak veći od ovoliko visine reda deli reči


@dataclass
class Word:
    box: tuple[int, int, int, int]  # x, y, širina, visina u isečku
    stroke: float  # debljina poteza / visina slova
    slant: float  # nagib slova u stepenima


@dataclass
class Line:
    box: tuple[int, int, int, int]
    words: list[Word] = field(default_factory=list)


def letter_mask(crop: Image.Image, inner: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Tamni potezi slova. Odbacuje se ono što dodiruje ivicu isečka (oblačić, crtež) i, uz `inner`
    (okvir bloka u isečku), sve čiji centar je van okvira."""
    gray = np.asarray(crop.convert("L"))
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask, connectivity=8)
    height, width = mask.shape
    keep = np.zeros(count, bool)
    for index in range(1, count):
        x, y, w, h, _area = stats[index]
        touches = x == 0 or y == 0 or x + w >= width or y + h >= height
        keep[index] = not touches and h < height * 0.9
        if inner is not None and keep[index]:
            cx, cy = centers[index]
            left, top, box_width, box_height = inner
            keep[index] = left <= cx <= left + box_width and top <= cy <= top + box_height
    return keep[labels]


def _runs(profile: np.ndarray) -> list[tuple[int, int]]:
    """Neprekinuti delovi gde je projekcija veća od nule: (početak, kraj)."""
    runs, start = [], None
    for index, value in enumerate(profile):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(profile)))
    return runs


def letter_height(mask: np.ndarray) -> float:
    """Visina slova: medijana delova bar upola visokih kao najviši (bez tačaka i zareza)."""
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    heights = stats[1:count, cv2.CC_STAT_HEIGHT]
    if not heights.size:
        return 0.0
    return float(np.median(heights[heights >= heights.max() * 0.5]))


def weight(mask: np.ndarray) -> float:
    """Debljina poteza u odnosu na visinu slova (ne zavisi od rezolucije skena)."""
    height = letter_height(mask)
    return _stroke(mask) / height if height else 0.0


def _stroke(mask: np.ndarray) -> float:
    """Srednja debljina poteza: 2 · površina / obim (obim tankog poteza je ~dvostruka dužina)."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
    return float(2 * mask.sum() / perimeter) if perimeter else 0.0


def slant(mask: np.ndarray) -> float:
    """Nagib slova u stepenima (udesno pozitivan): težinska medijana nagiba skoro uspravnih ivica.

    Maska se zamuti da ivice ne budu stepenaste. Kose crte uspravnih slova (A, V, M, W) idu na obe
    strane i poništavaju se, a kurziv pomera sve ivice na istu stranu.
    """
    blurred = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.5)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    edges = np.abs(gx) > 1e-6
    angles = np.degrees(np.arctan(gy[edges] / gx[edges]))
    weights = np.hypot(gx[edges], gy[edges])
    upright = np.abs(angles) < 40
    angles, weights = angles[upright], weights[upright]
    if not angles.size:
        return 0.0
    order = np.argsort(angles)
    cumulative = np.cumsum(weights[order])
    return float(angles[order][np.searchsorted(cumulative, cumulative[-1] / 2)])


MARGIN = (
    0.15  # isečak je veći od bloka: slova uz ivicu okvira ne smeju da se odbace kao ivica oblačića
)


def block_crop(
    image: Image.Image, x: float, y: float, width: float, height: float
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Isečak sa marginom i okvir bloka u njemu."""
    mx, my = width * MARGIN, height * MARGIN
    left, top = max(0, round(x - mx)), max(0, round(y - my))
    box = (
        left,
        top,
        min(image.width, round(x + width + mx)),
        min(image.height, round(y + height + my)),
    )
    return image.crop(box), (round(x) - left, round(y) - top, round(width), round(height))


def lines_and_words(crop: Image.Image, mask: np.ndarray | None = None) -> list[Line]:
    mask = letter_mask(crop) if mask is None else mask
    bands = _runs(mask.sum(axis=1) > 0)
    if not bands:
        return []
    typical = float(np.median([end - start for start, end in bands]))
    lines = []
    for top, bottom in bands:
        if bottom - top < typical * MIN_LINE_HEIGHT:
            continue
        band = mask[top:bottom]
        columns = _runs(band.sum(axis=0) > 0)
        gap = (bottom - top) * WORD_GAP
        groups: list[list[tuple[int, int]]] = []
        for run in columns:
            if groups and run[0] - groups[-1][-1][1] <= gap:
                groups[-1].append(run)
            else:
                groups.append([run])
        xs, xe = columns[0][0], columns[-1][1]
        line = Line((xs, top, xe - xs, bottom - top))
        for group in groups:
            left, right = group[0][0], group[-1][1]
            piece = band[:, left:right]
            line.words.append(
                Word(
                    (left, top, right - left, bottom - top),
                    weight(piece),
                    slant(piece),
                )
            )
        lines.append(line)
    return lines


# pragovi izmereni na dva broja (dva crtača), 1.182 bloka koje je korisnik označio
# (docs/benchmarks/naglasak.md)
NORMAL_WEIGHT = 0.154  # obična slova: debljina poteza / visina slova (medijana prvog broja)
BLOCK_WEIGHT, BLOCK_SLANT = 1.0, 8.0  # ceo blok: ukošen i bar uobičajene debljine (povik)
WORD_WEIGHT, WORD_SLANT = 1.05, 8.0  # pojedine reči (retke; preciznost je važnija od odziva)
WORD_MIN_LETTERS = 3  # kraći deo reda (A, MA) ima kose poteze slova koji liče na nagib
PLAIN_SHARE = 0.3  # ceo blok, osim ako je bar ovoliki deo reči običan (onda su to pojedine reči)
NARRATION_RECT = 0.93  # naracija je u pravougaoniku: ne naglašava se (ima svoju opciju serijala)


@dataclass
class Emphasis:
    block: bool = False  # ceo blok naglašen
    words: list[tuple[int, int]] = field(
        default_factory=list
    )  # (red, reč) naglašenih reči u tekstu


def rectangularity(polygon: list[list[float]] | None) -> float:
    """Površina oblika / površina okvira: pravougaonik 1, elipsa ~0,79."""
    if not polygon or len(polygon) < 3:
        return 0.0
    points = np.array(polygon, np.float32).reshape(-1, 2)
    _, _, width, height = cv2.boundingRect(points)
    return float(cv2.contourArea(points)) / (width * height) if width * height else 0.0


def _part_at(line: Line, x: float) -> int:
    """Indeks dela reda na položaju x (ili najbližeg, ako je x u razmaku)."""

    def distance(word: Word) -> float:
        start, end = word.box[0], word.box[0] + word.box[2]
        return 0.0 if start <= x <= end else min(abs(x - start), abs(x - end))

    return min(range(len(line.words)), key=lambda index: distance(line.words[index]))


def _word_parts(text_lines: list[str], lines: list[Line]) -> list[list[Word | None]]:
    """Za svaku reč teksta deo reda sa slike u kome je većina njenih slova (po položaju u redu)."""
    result = []
    for text, line in zip(text_lines, lines, strict=True):
        left, _, width, _ = line.box
        letter = width / max(len(text), 1)

        parts = [_part_at(line, left + (index + 0.5) * letter) for index in range(len(text))]
        words: list[Word | None] = []
        start = None
        for index, char in enumerate(text + " "):
            if char.isspace() and start is not None:
                chosen = parts[start:index]
                word = line.words[max(set(chosen), key=chosen.count)]
                long_enough = word.box[2] >= WORD_MIN_LETTERS * letter
                words.append(word if long_enough else None)
                start = None
            elif not char.isspace() and start is None:
                start = index
        result.append(words)
    return result


def _bold(word: Word | None) -> bool:
    return (
        word is not None and word.stroke / NORMAL_WEIGHT >= WORD_WEIGHT and word.slant >= WORD_SLANT
    )


def _plain(word: Word | None) -> bool:
    """Jasno obična reč: tanja od naglašenih i bez nagiba (kratke reči se ne računaju)."""
    return (
        word is not None
        and word.stroke / NORMAL_WEIGHT < BLOCK_WEIGHT
        and word.slant < BLOCK_SLANT / 2
    )


def analyze(
    image: Image.Image,
    box: tuple[float, float, float, float],
    text: str,
    polygon: list[list[float]] | None = None,
) -> Emphasis:
    """Naglasak bloka iz originala: ceo blok (povik) ili pojedine reči; naracija se ne naglašava."""
    if rectangularity(polygon) > NARRATION_RECT:
        return Emphasis()
    crop, inner = block_crop(image, *box)
    mask = letter_mask(crop, inner)
    if not mask.any():
        return Emphasis()
    ratio = weight(mask) / NORMAL_WEIGHT
    whole = ratio >= BLOCK_WEIGHT and slant(mask) >= BLOCK_SLANT
    text_lines = [line for line in text.splitlines() if line.strip()]
    lines = lines_and_words(crop, mask)
    if len(lines) != len(text_lines):
        return Emphasis(block=whole)  # redovi se ne poklapaju: reči se ne pogađaju
    parts = _word_parts(text_lines, lines)
    total = sum(len(line) for line in parts)
    plain = sum(_plain(word) for line in parts for word in line)
    if whole and (not total or plain / total < PLAIN_SHARE):
        return Emphasis(block=True)
    tokens = [line.split() for line in text_lines]
    words = [
        (row, index)
        for row, line in enumerate(parts)
        for index, word in enumerate(line)
        if _bold(word) and any(char.isalpha() for char in tokens[row][index])  # ne interpunkcija
    ]
    return Emphasis(words=words)


def mark(text: str, words: list[tuple[int, int]]) -> str:
    """Tekst sa `*…*` oko naglašenih reči; susedne naglašene reči u istom redu su jedan deo."""
    chosen = set(words)
    out_lines, row = [], 0
    for line in text.split("\n"):
        if not line.strip():
            out_lines.append(line)
            continue
        parts = line.split(" ")
        index, marked = 0, []
        for position, part in enumerate(parts):
            if not part:
                marked.append(part)
                continue
            bold = (row, index) in chosen
            before = position > 0 and (row, index - 1) in chosen and parts[position - 1] != ""
            after = (row, index + 1) in chosen and position + 1 < len(parts) and parts[position + 1]
            if bold:
                part = ("" if before else "*") + part + ("" if after else "*")
            marked.append(part)
            index += 1
        out_lines.append(" ".join(marked))
        row += 1
    return "\n".join(out_lines)


def _shape_without_text(gray: np.ndarray, box: tuple, bubble_shape, white: int) -> list | None:
    """Oblik oblačića pre čišćenja: slova prekidaju beli prostor, pa se za merenje privremeno
    izbele (čišćenje meri oblik tek na očišćenoj strani). Beli se samo ono što leži ceo unutar
    okvira teksta, da ivica okvira naracije ostane."""
    if not gray.flags.writeable:
        gray = gray.copy()
    height, width = gray.shape
    x, y, w, h = (int(round(value)) for value in box)
    left, top = max(x, 0), max(y, 0)
    right, bottom = min(x + w, width), min(y + h, height)
    if right <= left or bottom <= top:
        return bubble_shape(gray, box)
    region = gray[top:bottom, left:right]
    dark = (region <= white).astype(np.uint8)  # i siva ivica slova, ne samo jezgro
    count, labels, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    inner = np.zeros(count, bool)
    for index in range(1, count):
        cx, cy, cw, ch, _area = stats[index]
        touches = cx == 0 or cy == 0 or cx + cw >= region.shape[1] or cy + ch >= region.shape[0]
        inner[index] = not touches
    letters = inner[labels].astype(np.uint8)
    letters = (cv2.dilate(letters, np.ones((5, 5), np.uint8)) > 0) & (region <= white)
    saved = region[letters].copy()
    region[letters] = 255
    try:
        return bubble_shape(gray, box)
    finally:
        region[letters] = saved


EMPHASIS_KINDS = {"speech", "thought", "caption"}  # onomatopeje i natpisi imaju svoj izgled


def apply(block: TextBlock, image: Image.Image, gray: np.ndarray) -> bool:
    """Naglasak iz originala upisan u blok: ceo blok → `style.emphasis`, reči → `*…*` u tekstu.

    Postojeće oznake (ručne ili ranije) se ne diraju. Vraća True ako je nešto upisano.
    """
    from app.services.cleaning import WHITE, bubble_shape  # cleaning uvozi page_processing

    if block.kind not in EMPHASIS_KINDS or not block.text.strip() or "*" in block.text:
        return False
    box = (block.x, block.y, block.width, block.height)
    # upisan oblik ne važi: detekcija upiše pravougaonik okvira, a čišćenje meri tek kasnije
    polygon = _shape_without_text(gray, box, bubble_shape, WHITE)
    found = analyze(image, box, block.text, polygon)
    if found.block:
        if (block.style or {}).get("emphasis"):
            return False
        block.style = {**(block.style or {}), "emphasis": True}
        return True
    if found.words:
        block.text = mark(block.text, found.words)
        return True
    return False
