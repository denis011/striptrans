"""Naslov od slova originala (Faza 6a).

Slova naslova priče (npr. belim „raščupanim" slovima na crnoj traci) seku se iz originala
kao slike, a prevod se slaže od njih, kao što su srpski izdavači radili u Photoshopu.
Slova kojih u originalu nema prave se automatski: slovo osnovnog fonta iste visine, širine i
debljine poteza kao slova originala, sa ivicama iste hrapavosti. Kvačice i akcenti se dodaju na
slova originala (S → Š).
"""

import io
import re
import shutil
import uuid
import zlib
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import object_session

from app.models import Font, TextBlock
from app.paths import inside
from app.services.geometry import Box

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
# osnove slova kojih nema u originalu (OFL); za naslov se bira ona koja najviše liči na original
FONTS = (
    ("Archivo Black", FONT_DIR / "ArchivoBlack-Regular.ttf"),  # debela bez serifa (crtani naslovi)
    ("Roboto Serif", FONT_DIR / "RobotoSerif-CondensedBlack.ttf"),  # zbijeni serif (štampani)
    (
        "Anton",
        FONT_DIR / "Anton-Regular.ttf",
    ),  # zbijena debela bez serifa (naslovi priča, šuplja slova)
)
CHARSET = "ABCČĆDĐEFGHIJKLMNOPQRSŠTUVWXYZŽ0123456789!?.,-:'\""
ACCENTED = {"Š": "S", "Č": "C", "Ć": "C", "Ž": "Z", "Đ": "D"}
GROW = 0.05  # okvir bloka ume da ne obuhvati celo slovo
MIN_PART = 20  # px; manji delovi su prašina skena
DOT = 0.018  # ...kod sitnih slova tačka je manja: prag je najviše ovaj deo kvadrata visine slova
NOISE = 0.01  # delovi manji od 1 % najvećeg su tekstura, ne slova
SHORT = 0.5  # delovi niži od pola tipičnog slova pripadaju susednom (tačka, kvačica)
OVERLAP = 0.5  # ...ako se sa njim preklapaju bar pola svoje širine
MERGE = 0.7  # slomljeno slovo: delovi se po širini preklapaju bar 70 % užeg dela
BREAK = 0.25  # ...i razmaknuti su najviše četvrtinu visine slova
JOINED = 1.6  # spojena slova: oblik bar 1,6× širi od ostalih
THIN = 0.35  # ...sa mestom spoja tanjim od trećine uobičajenog stupca mastila
PAD = 3  # prazan rub oko slova u slici (px)
BODY = 0.5  # bela unutrašnjost šupljeg slova je bar upola visoka kao okvir naslova
RING = 0.12  # kontura šupljeg slova se traži u pojasu ovolikog dela visine slova
THICK = 0.05  # unutrašnjost slova je bar ovoliko debela (poluprečnik upisanog kruga / visina)
PAPER_SHARE = 0.85  # rupa u slovu je ispuna ako je bar ovoliko njenih piksela boje papira
MIN_FILL = 0.05  # ispuna se pamti ako je bar ovoliki deo slova
CLOSE_GAP = 0.03  # pukotine konture do ovog dela visine slova se zatvaraju pre traženja ispune
SOFT = 2  # meka ivica: maska se proširi pre računanja providnosti
CLEAN_DILATE = 5  # čišćenje: proširenje maske slova (sive ivice)
TOLERANCE = 40  # razlika od boje trake koja se još smatra trakom
FREE_SHARE = 0.98  # red iznad/ispod slova je slobodan ako je ovoliko piksela boje trake
GROWTH_USE = 0.8  # uvećanje sme da iskoristi ovoliki deo slobodnog prostora
MAX_SCALE = 1.5
UNIFORM_STD = 25  # traka je jednobojna (ispuna bojom); inače LaMa
SMOOTH = 0.04  # hrapavost se meri prema slovu zaglađenom ovolikim delom visine
ROUGH = 1.3  # original je „raščupan" ako mu je ivica bar ovoliko hrapavija od ivice fonta
WAVE = ((1.0, 0.04), (0.3, 0.015))  # talasi „raščupane" ivice: (težina, veličina u visinama slova)
SPECK = (0.02, 0.005)  # ostrvca i rupice (udeo slova) su mrlje od šuma; prave rupe (A, R) su veće
HOLLOW = 0.55  # šuplja slova: unutrašnjost je veća od ovog dela ispunjenog slova
SAME_HEIGHT = 0.15  # tela šupljih slova jednog naslova su iste visine, do ovoliko odstupanja
MIN_ANGLE = 2.0  # manji nagib reda teksta se ne ispravlja (stepeni)
MAX_ANGLE = 30.0  # strmije trake u stripu skoro da nema, a šrafura crteža ume da prevari merenje
ROW_SPREAD = 0.3  # posle ispravljanja središta slova odstupaju od reda najviše ovoliko visine slova
BAND = 1.3  # kos naslov: posle ispravljanja okvir obuhvata red teksta ± ovoliko visina slova
MAX_SLANT = 20  # nagib slova se traži do ovoliko stepeni
MIN_SLANT = 3  # manji nagib je uspravno slovo
HAIR = 0.012  # šiljci tanji od ovoga (u visinama slova) se odsecaju
SUPER = 4  # slovo fonta se crta ovoliko uvećano, pa se smanjuje (ivica bez stepenica)
SOFT_SIGMA = 0.35  # dodatno zaglađivanje smanjenog slova (px), do mekoće ivice skena
MARK_GAP = 0.7  # kvačica je bliže slovu nego u fontu, kao u ručnom letteringu
VERSIONS = 6  # koliko verzija slova ostaje na disku (starije se brišu; služe za „Poništi")


@dataclass
class Glyph:
    char: str
    alpha: np.ndarray  # providnost slova (uint8), sa rubom PAD
    baseline: float  # red osnovne linije u slici (od vrha slike)
    ink_left: float  # prvi i poslednji stubac mastila u slici
    ink_right: float
    source: str = "original"  # original | fallback | accent | custom
    font: str = ""  # napravljeno slovo: font od koga je
    box: tuple[int, int, int, int] | None = None  # original: položaj slike na stranici (x, y, w, h)
    row: int = 0
    space_before: bool = False
    gap_next: float | None = None  # razmak do sledećeg slova originala u istom redu
    fill: np.ndarray | None = (
        None  # ispuna (unutrašnjost šupljeg slova, boja papira), iste veličine
    )


@dataclass
class Letters:
    glyphs: list[Glyph]
    light: bool  # svetla slova na tamnoj podlozi
    ink: float  # siva slova
    background: float  # siva podloge
    uniform: bool  # podloga je jednobojna
    mask: np.ndarray  # piksela slova na stranici (za čišćenje)
    expected: int  # broj slova u tekstu originala
    extent: tuple[float, float, float, float]  # levo, gore, desno, dole (mastilo svih slova)
    cap_height: float
    free: float  # slobodan prostor boje trake iznad i ispod slova (px)
    word_gap: float
    gap: float  # medijana razmaka susednih slova
    extra: list[Glyph] = field(default_factory=list)  # slova kojih nema u originalu
    font: str = ""  # font od koga su napravljena slova koja nedostaju (automatski izbor)
    fonts: list[str] = field(default_factory=list)  # fontovi koji se mogu izabrati po slovu
    paper: float | None = None  # boja unutrašnjosti šupljih slova (papir)
    slant: float = 0.0  # nagib slova originala (tangens, udesno pozitivan)
    hollow: bool = False  # slova originala su samo kontura
    # kos naslov: red teksta je nagnut za `angle` stepeni (u smeru kazaljke, + = spušta se udesno);
    # slova se seku i slažu na stranici zarotiranoj oko `center`, pa se složen naslov vraća pod ugao
    angle: float = 0.0
    center: tuple[float, float] | None = None
    skew: float = 0.0  # kos naslov u kurzivu: nagib slova (tangens) koji je skinut pre sečenja

    @property
    def mismatch(self) -> bool:
        return len(self.glyphs) != self.expected


def _labels(text: str) -> list[str]:
    return [char for char in text.upper() if not char.isspace()]


def _ranges_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return min(a1, b1) - max(a0, b0)


def _hollow_labels(
    ink: np.ndarray, box: tuple[int, int, int, int], expected: int
) -> tuple[np.ndarray, np.ndarray] | None:
    """Oznake slova po beloj unutrašnjosti: po jedna zatvorena bela površina visine slova po slovu.

    Vraća konture (mastilo u pojasu oko površine) i same unutrašnjosti, obe označene istim brojem
    slova; None ako se broj površina ne poklapa sa brojem slova teksta (tada važi obično isecanje
    po oblicima mastila).
    """
    left, top, right, bottom = box
    count, labels, stats, centers = cv2.connectedComponentsWithStats(
        (~ink).astype(np.uint8), connectivity=4
    )
    bodies = []
    for i in range(1, count):
        bx, by, bw, bh, _ = stats[i]
        cx, cy = centers[i]
        inside = left <= cx <= right and top <= cy <= bottom
        # papir oko slova je veći od jednog slova; slovo sme da dodiruje ivicu okvira
        letter = BODY * (bottom - top) <= bh <= 1.15 * (bottom - top) and bw <= 0.6 * (right - left)
        if not (inside and letter):
            continue
        # unutrašnjost slova je puna površina, a bele pruge između linija crteža su tanke
        region = (labels[by : by + bh, bx : bx + bw] == i).astype(np.uint8)
        thickness = cv2.distanceTransform(np.pad(region, 1), cv2.DIST_L2, 5).max()
        if thickness >= THICK * (bottom - top):
            bodies.append(i)
    if len(bodies) > expected:
        # bela pozadina između slova (nebo, papir iza crteža) ume da liči na telo slova, ali nije
        # iste visine kao slova naslova: odbacuju se površine koje odstupaju od srednje visine
        typical = float(np.median([stats[i, cv2.CC_STAT_HEIGHT] for i in bodies]))
        bodies = [
            i
            for i in bodies
            if abs(stats[i, cv2.CC_STAT_HEIGHT] - typical) <= SAME_HEIGHT * typical
        ]
    if len(bodies) < 2 or len(bodies) != expected:
        return None
    band = max(3, round(RING * float(np.median([stats[i, cv2.CC_STAT_HEIGHT] for i in bodies]))))
    # debljina konture je ista za sva slova naslova: medijana neprekinutog mastila od ivice tela
    # ka spolja. Linije crteža koje dodiruju konturu produže samo pojedine nizove, pa ne menjaju
    # medijanu (ranije se debljina merila po slovu i gutala crtež oko slova)
    thickness = min(band, _outline_thickness(ink, labels, bodies, stats))
    result = np.zeros(ink.shape, np.int32)
    interiors = np.zeros(ink.shape, np.int32)
    for number, i in enumerate(bodies, start=1):
        distance = cv2.distanceTransform((labels != i).astype(np.uint8), cv2.DIST_L2, 5)
        ring = ink & (distance <= thickness + 1)
        result[ring & (result == 0)] = number
        interiors[labels == i] = number
    return result, interiors


def _outline_thickness(
    ink: np.ndarray, labels: np.ndarray, bodies: list[int], stats: np.ndarray
) -> int:
    """Debljina konture šupljih slova: medijana dužine mastila od ivice unutrašnjosti ka spolja."""

    def run(line: np.ndarray) -> int:
        stop = np.flatnonzero(~line)
        return int(stop[0]) if len(stop) else len(line)

    runs = []
    for i in bodies:
        left, top, width, height, _ = stats[i]
        own = labels[top : top + height, left : left + width] == i
        for column in range(width // 4, 3 * width // 4 + 1, 3):
            rows = np.flatnonzero(own[:, column])
            if len(rows):
                runs.append(run(ink[top + rows[0] - 1 :: -1, left + column]))
                runs.append(run(ink[top + rows[-1] + 1 :, left + column]))
        for row in range(height // 4, 3 * height // 4 + 1, 3):
            cols = np.flatnonzero(own[row])
            if len(cols):
                runs.append(run(ink[top + row, left + cols[0] - 1 :: -1]))
                runs.append(run(ink[top + row, left + cols[-1] + 1 :]))
    return max(2, round(float(np.median(runs)))) if runs else 3


def _paper_fill(
    own: np.ndarray, crop: np.ndarray, threshold: float, light: bool, typical: float
) -> np.ndarray | None:
    """Šuplje slovo: kontura + zatvorene rupe boje papira (unutrašnjost slova, ne crtež)."""
    size = 2 * max(1, round(CLOSE_GAP * typical)) + 1
    closed = cv2.morphologyEx(
        own.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)),
    ).astype(bool)
    holes = _fill_holes(closed) & ~closed
    count, labels = cv2.connectedComponents(holes.astype(np.uint8), connectivity=4)
    paper = crop < threshold if light else crop > threshold
    fill = closed.copy()
    for i in range(1, count):
        region = labels == i
        if paper[region].mean() >= PAPER_SHARE:
            fill |= region
    return fill if (fill & ~own).sum() >= MIN_FILL * max(1, own.sum()) else None


def _part_stats(mask: np.ndarray) -> list[int]:
    """Okvir i površina dela (kao red iz cv2.connectedComponentsWithStats)."""
    rows, cols = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    if not len(rows):
        return [0, 0, 0, 0, 0]
    return [
        int(cols[0]),
        int(rows[0]),
        int(cols[-1] - cols[0] + 1),
        int(rows[-1] - rows[0] + 1),
        int(mask.sum()),
    ]


@lru_cache(maxsize=1)
def _reference_font() -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / "ComicNeue-Bold.ttf"), 100)


@lru_cache(maxsize=256)
def _char_width(char: str) -> float:
    """Uobičajena širina slova u visinama velikog slova (za poravnanje oblika sa tekstom)."""
    font = _reference_font()
    cap = -font.getbbox("H", anchor="ls")[1]
    left, _, right, _ = font.getbbox(char, anchor="ls")
    return max(0.15, (right - left) / max(cap, 1))


def _reading_key(bounds: tuple[int, int, int, int], typical: float) -> tuple[int, float]:
    """Redosled čitanja oblika: red (po visini, u koracima visine slova), pa sleva nadesno."""
    left, top, right, bottom = bounds
    return int(((top + bottom) / 2) // max(typical, 1.0)), (left + right) / 2


def _cover(widths: list[float], chars: list[str]) -> list[list[str]] | None:
    """Koja slova teksta nosi svaki oblik (1–3 slova), tako da se širine najbolje poklope.

    Dinamičko poravnanje: oblik koji nosi dva slova treba da bude širok kao ta dva slova zajedno.
    """
    count, total = len(widths), len(chars)
    if not count or total < count or total > 3 * count:
        return None
    sizes = [_char_width(char) for char in chars]
    scale = sum(widths) / sum(sizes)
    infinity = float("inf")
    cost = [[infinity] * (total + 1) for _ in range(count + 1)]
    step = [[0] * (total + 1) for _ in range(count + 1)]
    cost[0][0] = 0.0
    for i in range(1, count + 1):
        for j in range(i, min(total, 3 * i) + 1):
            for k in (1, 2, 3):
                if j - k < i - 1 or cost[i - 1][j - k] == infinity:
                    continue
                expected = scale * sum(sizes[j - k : j])
                value = (
                    cost[i - 1][j - k] + abs(widths[i - 1] - expected) / expected + 0.3 * (k - 1)
                )
                if value < cost[i][j]:
                    cost[i][j], step[i][j] = value, k
    if cost[count][total] == infinity:
        return None
    plan, j = [], total
    for i in range(count, 0, -1):
        k = step[i][j]
        plan.append(chars[j - k : j])
        j -= k
    return plan[::-1]


def _letter_parts(
    gray: np.ndarray, box: Box
) -> tuple[np.ndarray, list[tuple[float, float, float]]]:
    """Delovi mastila veličine slova u okviru: središte x i y i visina, u pikselima okvira."""
    x, y, w, h = (int(round(value)) for value in box)
    roi = gray[max(y, 0) : y + h, max(x, 0) : x + w]
    if roi.size == 0:
        return roi, []
    light = float(np.median(roi)) < 128
    threshold, _ = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = roi > threshold if light else roi < threshold
    count, _, stats, centers = cv2.connectedComponentsWithStats(
        ink.astype(np.uint8), connectivity=8
    )
    parts = [
        i
        for i in range(1, count)
        if stats[i, cv2.CC_STAT_AREA] >= MIN_PART
        and stats[i, cv2.CC_STAT_WIDTH] < 0.5 * roi.shape[1]
        and stats[i, cv2.CC_STAT_HEIGHT] < 0.9 * roi.shape[0]
    ]
    if not parts:
        return roi, []
    typical = float(np.median([stats[i, cv2.CC_STAT_HEIGHT] for i in parts]))
    letters = [
        (float(centers[i][0]), float(centers[i][1]), float(stats[i, cv2.CC_STAT_HEIGHT]))
        for i in parts
        if 0.5 * typical <= stats[i, cv2.CC_STAT_HEIGHT] <= 1.6 * typical
    ]
    return roi, letters


def _text_angle(gray: np.ndarray, box: Box) -> float:
    """Nagib reda teksta u okviru (stepeni, u smeru kazaljke; + = red se spušta udesno).

    Meri se nagib između svakog slova i njegovog najbližeg suseda desno; medijana ne mari za
    pojedine delove crteža ni za više redova naslova. 0 ako je red praktično vodoravan.
    """
    _, parts = _letter_parts(gray, box)
    if len(parts) < 4:
        return 0.0
    typical = float(np.median([height for _, _, height in parts]))
    slopes = []
    for cx, cy, _ in parts:
        neighbours = [
            (ox - cx, oy - cy)
            for ox, oy, _ in parts
            if 0 < ox - cx < 3 * typical and abs(oy - cy) < ox - cx
        ]
        if neighbours:
            dx, dy = min(neighbours)
            slopes.append(dy / dx)
    if len(slopes) < 3:
        return 0.0
    slope = float(np.median(slopes))
    angle = float(np.degrees(np.arctan(slope)))
    if not MIN_ANGLE <= abs(angle) <= MAX_ANGLE:
        return 0.0
    # nagib važi samo ako slova posle njega stvarno leže u jednom redu, a vodoravno ne: šrafura
    # crteža (kose linije) daje „nagib" iako slova stoje vodoravno
    xs = np.array([cx for cx, _, _ in parts])
    ys = np.array([cy for _, cy, _ in parts])
    tilted = ys - slope * xs
    tilted_spread = float(np.median(np.abs(tilted - np.median(tilted))))
    level_spread = float(np.median(np.abs(ys - np.median(ys))))
    if tilted_spread > ROW_SPREAD * typical or level_spread < 2 * tilted_spread:
        return 0.0
    return angle


def find_letters(gray: np.ndarray, box: Box, text: str) -> Letters | None:
    """Iseci slova naslova iz okvira bloka i upari ih sa slovima teksta originala.

    Kos naslov (traka sa potpisom, natpis na tabli) se prvo ispravi: stranica se zarotira oko
    sredine okvira tako da red bude vodoravan, a slova u kurzivu se usprave; tako se seku kao
    obična uspravna slova. Maska za čišćenje se vraća u prostor stranice, a frontend složen prevod
    vraća pod isti ugao i u isti kurziv (`angle`, `skew`, `center`).
    """
    angle = _text_angle(gray, box)
    if not angle:
        return _find_letters(gray, box, text)
    x, y, w, h = box
    center = (x + w / 2, y + h / 2)
    height, width = gray.shape

    def warp(image: np.ndarray, matrix: np.ndarray, nearest: bool = False) -> np.ndarray:
        return cv2.warpAffine(
            image,
            matrix[:2],
            (width, height),
            flags=cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

    # cv2: pozitivan ugao okreće suprotno od kazaljke, pa ispravlja red koji se spušta udesno
    rotate = np.vstack([cv2.getRotationMatrix2D(center, angle, 1.0), [0, 0, 1]])
    straight = warp(gray, rotate)
    # posle ispravljanja okvir se sužava na red teksta, da crtež iznad i ispod trake ne uđe
    roi, parts = _letter_parts(straight, box)
    if not parts:
        return None
    typical = float(np.median([part_height for _, _, part_height in parts]))
    middle = float(np.median([cy for _, cy, _ in parts])) + max(y, 0)
    band = (x, middle - BAND * typical, w, 2 * BAND * typical)
    # kurziv: slova se usprave (smicanje oko sredine okvira), da se ne preklapaju po širini
    band_roi = straight[int(max(band[1], 0)) : int(band[1] + band[3]), int(x) : int(x + w)]
    threshold, _ = cv2.threshold(band_roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    light = float(np.median(band_roi)) < 128
    ink = band_roi > threshold if light else band_roi < threshold
    skew = _slant([ink]) if ink.any() else 0.0
    shear = np.array([[1.0, skew, -skew * center[1]], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    forward = shear @ rotate
    upright = warp(gray, forward) if skew else straight
    letters = _find_letters(upright, band, text)
    if letters is None:
        return None
    letters.mask = warp(letters.mask.astype(np.uint8), np.linalg.inv(forward), nearest=True) > 0
    letters.angle = angle
    letters.skew = skew
    letters.center = center
    return letters


def _find_letters(gray: np.ndarray, box: Box, text: str) -> Letters | None:
    """Isecanje slova vodoravnog naslova (videti `find_letters`)."""
    height, width = gray.shape
    x, y, w, h = box
    x0, y0 = max(int(x - w * GROW), 0), max(int(y - h * GROW), 0)
    x1, y1 = (
        min(int(np.ceil(x + w * (1 + GROW))), width),
        min(int(np.ceil(y + h * (1 + GROW))), height),
    )
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return None
    light = float(np.median(roi)) < 128
    threshold, _ = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = roi > threshold if light else roi < threshold
    count, labels, stats, centers = cv2.connectedComponentsWithStats(
        ink.astype(np.uint8), connectivity=8
    )
    by_bodies = False  # slova nađena po unutrašnjosti (šuplja slova preko crteža)
    interiors = None
    if not light:
        # šuplja slova preko crteža (bela sa crnom konturom): kontura dodiruje crtež, pa se slova
        # traže po beloj unutrašnjosti koju kontura zatvara
        inner = (int(x - x0), int(y - y0), int(x + w - x0), int(y + h - y0))
        hollow = _hollow_labels(ink, inner, len(_labels(text)))
        if hollow is not None:
            by_bodies = True
            labels, interiors = hollow
            count = int(labels.max()) + 1
            stats = np.array(
                [[0, 0, 0, 0, 0]] + [_part_stats(labels == i) for i in range(1, count)]
            )
            centers = np.array(
                [[0.0, 0.0]] + [[s[0] + s[2] / 2, s[1] + s[3] / 2] for s in stats[1:]]
            )
    # sitna slova (potpis na traci): tačke dvotačke su manje od praga za prašinu, pa se prag
    # spušta srazmerno visini slova (krupni naslovi zadržavaju isti prag)
    sizes = [stats[i, cv2.CC_STAT_HEIGHT] for i in range(1, count) if stats[i, 4] >= MIN_PART]
    letter_size = float(np.median(sizes)) if sizes else 0.0
    min_part = min(MIN_PART, max(4.0, DOT * letter_size**2)) if sizes else MIN_PART
    candidates = []
    for i in range(1, count):
        left, top, part_w, part_h, area = stats[i]
        cx, cy = centers[i][0] + x0, centers[i][1] + y0
        # podloga, ne slovo (slova nađena po unutrašnjosti su sigurno slova)
        slab = not by_bodies and (part_w > 0.9 * roi.shape[1] or part_h > 0.9 * roi.shape[0])
        if area >= min_part and x <= cx <= x + w and y <= cy <= y + h and not slab:
            candidates.append(i)
    if not candidates:
        return None
    largest = max(stats[i, cv2.CC_STAT_AREA] for i in candidates)
    # najveći deo ume da bude ivica trake ili crtež, pa tačka dvotačke ne sme da ispadne kao šum
    noise = min(NOISE * largest, max(min_part, DOT * letter_size**2))
    parts = [i for i in candidates if stats[i, cv2.CC_STAT_AREA] >= noise]
    # niski delovi (tačka, kvačica, zarez) pripadaju slovu iznad ili ispod sebe; visoki uski
    # delovi („!", „I") su slova za sebe
    heights = [
        stats[i, cv2.CC_STAT_HEIGHT] for i in parts if stats[i, cv2.CC_STAT_AREA] >= 0.2 * largest
    ]
    typical = float(np.median(heights))
    tall = [i for i in parts if stats[i, cv2.CC_STAT_HEIGHT] >= SHORT * typical]
    groups: dict[int, list[int]] = {i: [i] for i in tall}
    for i in parts:
        if i in groups:
            continue
        left, top, part_w, part_h, _ = stats[i]
        best, best_distance = None, None
        for j in tall:
            overlap = _ranges_overlap(left, left + part_w, stats[j, 0], stats[j, 0] + stats[j, 2])
            beside = _ranges_overlap(top, top + part_h, stats[j, 1], stats[j, 1] + stats[j, 3])
            if overlap < OVERLAP * part_w or beside > OVERLAP * part_h:
                continue
            distance = max(0, -beside)
            if best_distance is None or distance < best_distance:
                best, best_distance = j, distance
        if best is None:
            groups[i] = [i]
        else:
            groups[best].append(i)
    # dvotačka: dva niska dela jedan iznad drugog, bez slova uz sebe, su jedan znak
    lone = sorted(
        (i for i, members in groups.items() if members == [i] and i not in tall),
        key=lambda i: stats[i, 1],
    )
    for upper_index, upper in enumerate(lone):
        if upper not in groups:
            continue
        for lower in lone[upper_index + 1 :]:
            if lower not in groups:
                continue
            u_left, u_top, u_w, u_h, _ = stats[upper]
            l_left, l_top, l_w, l_h, _ = stats[lower]
            across = _ranges_overlap(u_left, u_left + u_w, l_left, l_left + l_w)
            gap = l_top - (u_top + u_h)
            if across >= OVERLAP * min(u_w, l_w) and 0 <= gap <= typical:
                groups[upper] += groups.pop(lower)
                break

    def bounds(members: list[int]) -> tuple[int, int, int, int]:
        return (
            min(stats[m, 0] for m in members),
            min(stats[m, 1] for m in members),
            max(stats[m, 0] + stats[m, 2] for m in members),
            max(stats[m, 1] + stats[m, 3] for m in members),
        )

    # slomljeno slovo: delovi jedan iznad drugog ili jedan u drugom se spajaju, dok broj ne
    # odgovara tekstu (slova koja se samo uvlače jedno pod drugo se preklapaju manje)
    expected = _labels(text)
    items = list(groups.values())
    while len(items) > len(expected):
        best, pair = (MERGE, 0.0), None
        for a_index, a_members in enumerate(items):
            for b_index in range(a_index + 1, len(items)):
                a, b = bounds(a_members), bounds(items[b_index])
                ratio = _ranges_overlap(a[0], a[2], b[0], b[2]) / max(
                    1, min(a[2] - a[0], b[2] - b[0])
                )
                distance = max(0, -_ranges_overlap(a[1], a[3], b[1], b[3]))
                if distance <= BREAK * typical and (ratio, -distance) > best:
                    best, pair = (ratio, -distance), (a_index, b_index)
        if pair is None:
            break
        items[pair[0]] = items[pair[0]] + items.pop(pair[1])

    # spojena slova (dodiruju se serifom ili ukrasom, npr. MA na str. 3): najširi oblik se seče
    # na najtanjem mestu srednjeg dela, dok broj ne odgovara tekstu
    while items and len(items) < len(expected):
        widths = [bounds(members)[2] - bounds(members)[0] for members in items]
        widest = int(np.argmax(widths))
        others = [w for i, w in enumerate(widths) if i != widest] or widths
        if widths[widest] < JOINED * float(np.median(others)):
            break
        members = items[widest]
        left, top, right, bottom = bounds(members)
        column = np.isin(labels[top:bottom, left:right], members).sum(axis=0)
        low, high = int(len(column) * 0.25), int(len(column) * 0.75)
        cut = low + int(np.argmin(column[low:high]))
        if column[cut] > THIN * float(np.median(column[column > 0])):
            break
        new = int(labels.max()) + 1
        region = labels[top:bottom, left + cut : right]
        region[np.isin(region, members)] = new
        stats = np.vstack([stats, _part_stats(labels == new)])
        for member in members:
            stats[member] = _part_stats(labels == member)
        items[widest] = [member for member in members if stats[member, cv2.CC_STAT_AREA]]
        items.insert(widest + 1, [new])

    # rukom pisan potpis: uska slova se dodiruju (D i I), pa oblik nije mnogo širi od ostalih.
    # Poravnanje oblika sa slovima teksta po širinama kaže koji oblik nosi dva slova i gde ga seći
    while items and len(items) < len(expected):
        order = sorted(range(len(items)), key=lambda k: _reading_key(bounds(items[k]), typical))
        widths = [bounds(items[k])[2] - bounds(items[k])[0] for k in order]
        plan = _cover(widths, expected)
        if plan is None:
            break
        spot = next((k for k, chars in zip(order, plan, strict=True) if len(chars) > 1), None)
        if spot is None:
            break
        chars = plan[order.index(spot)]
        members = items[spot]
        left, top, right, bottom = bounds(members)
        column = np.isin(labels[top:bottom, left:right], members).sum(axis=0)
        share = _char_width(chars[0]) / sum(_char_width(char) for char in chars)
        aim = len(column) * share
        low, high = max(1, int(0.15 * len(column))), min(len(column) - 1, int(0.85 * len(column)))
        if high <= low:
            break
        # najmanje mastila u stupcu, uz kaznu za udaljenost od očekivanog mesta: unutrašnjost
        # slova D je takođe tanka, ali je dalje od granice slova nego pravi procep
        ink_scale = max(1.0, float(np.median(column[column > 0])))
        scores = [column[c] / ink_scale + 2 * abs(c - aim) / len(column) for c in range(low, high)]
        cut = low + int(np.argmin(scores))
        new = int(labels.max()) + 1
        region = labels[top:bottom, left + cut : right]
        region[np.isin(region, members)] = new
        stats = np.vstack([stats, _part_stats(labels == new)])
        for member in members:
            stats[member] = _part_stats(labels == member)
        items[spot] = [member for member in members if stats[member, cv2.CC_STAT_AREA]]
        items.insert(spot + 1, [new])

    # redovi naslova (gore → dole), pa slova u redu (levo → desno)
    items.sort(key=lambda members: bounds(members)[1])
    rows: list[list[list[int]]] = []
    for members in items:
        _, top, _, bottom = bounds(members)
        for row in rows:
            row_top = min(bounds(m)[1] for m in row)
            row_bottom = max(bounds(m)[3] for m in row)
            if _ranges_overlap(top, bottom, row_top, row_bottom) >= 0.5 * min(
                bottom - top, row_bottom - row_top
            ):
                row.append(members)
                break
        else:
            rows.append([members])
    for row in rows:
        row.sort(key=lambda members: (bounds(members)[0] + bounds(members)[2]) / 2)

    all_mask = np.isin(labels, [m for row in rows for members in row for m in members])
    near = cv2.dilate(all_mask.astype(np.uint8), np.ones((11, 11), np.uint8)).astype(bool)
    ring = cv2.dilate(all_mask.astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool) & ~near
    background = float(np.median(roi[~near])) if (~near).any() else (0.0 if light else 255.0)
    ink_level = float(np.median(roi[all_mask]))
    uniform = bool(ring.any()) and float(np.std(roi[ring])) < UNIFORM_STD
    span = max(1.0, abs(ink_level - background))

    starts, total = set(), 0  # redni brojevi slova kojima počinje nova reč
    for word in text.upper().split():
        if total:
            starts.add(total)
        total += len(word)

    glyphs: list[Glyph] = []
    fills = np.zeros_like(all_mask)  # ispune svih slova (za čišćenje celog slova)
    paper_pixels: list[np.ndarray] = []
    for r, row in enumerate(rows):
        heights = [bounds(m)[3] - bounds(m)[1] for m in row]
        tall = [m for m, hh in zip(row, heights, strict=True) if hh >= 0.6 * max(heights)]
        baseline = float(np.median([bounds(m)[3] for m in tall])) + y0
        for members in row:
            left, top, right, bottom = bounds(members)
            cx0, cy0 = max(left - PAD, 0), max(top - PAD, 0)
            cx1, cy1 = min(right + PAD, roi.shape[1]), min(bottom + PAD, roi.shape[0])
            own = np.isin(labels[cy0:cy1, cx0:cx1], members)
            soft = cv2.dilate(own.astype(np.uint8), np.ones((SOFT * 2 + 1,) * 2, np.uint8)).astype(
                bool
            )
            crop = roi[cy0:cy1, cx0:cx1].astype(np.float32)
            level = (crop - background) / span if light else (background - crop) / span
            alpha = (np.clip(level, 0, 1) * soft * 255).astype(np.uint8)
            if interiors is not None:
                # šuplje slovo nađeno po unutrašnjosti: ispuna je baš ta unutrašnjost (malo
                # proširena pod konturu), a ne rupe konture, koje crtež ume da „probije"
                body = np.isin(interiors[cy0:cy1, cx0:cx1], members)
                fill = cv2.dilate(body.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
            else:
                fill = _paper_fill(own, crop, threshold, light, typical)
            if fill is not None:
                fills[cy0:cy1, cx0:cx1] |= fill
                paper_pixels.append(crop[fill & ~own])
            index = len(glyphs)
            glyphs.append(
                Glyph(
                    char=expected[index] if index < len(expected) else "?",
                    alpha=alpha,
                    fill=None if fill is None else _soft(fill),
                    baseline=baseline - (cy0 + y0),
                    ink_left=float(left - cx0),
                    ink_right=float(right - cx0),
                    box=(int(cx0 + x0), int(cy0 + y0), int(cx1 - cx0), int(cy1 - cy0)),
                    row=r,
                    space_before=index in starts,
                )
            )
    gaps, word_gaps = [], []
    for current, following in zip(glyphs, glyphs[1:], strict=False):
        if current.row != following.row:
            continue
        gap = (following.box[0] + following.ink_left) - (current.box[0] + current.ink_right)
        current.gap_next = float(gap)
        (word_gaps if following.space_before else gaps).append(gap)
    ink_boxes = [
        (g.box[0] + g.ink_left, g.box[1] + g.baseline, g.box[0] + g.ink_right) for g in glyphs
    ]
    left = min(b[0] for b in ink_boxes)
    right = max(b[2] for b in ink_boxes)
    top = float(min(bounds(m)[1] for row in rows for m in row) + y0)
    bottom = float(max(bounds(m)[3] for row in rows for m in row) + y0)
    caps = []
    for row in rows:
        heights = [bounds(m)[3] - bounds(m)[1] for m in row]
        caps += [hh for hh in heights if hh >= 0.6 * max(heights)]
    cap_height = float(np.median(caps))
    median_gap = float(np.median(gaps)) if gaps else 0.1 * cap_height
    word_gap = float(np.median(word_gaps)) if word_gaps else median_gap + 0.35 * cap_height

    mask = np.zeros((height, width), dtype=bool)
    mask[y0:y1, x0:x1] = cv2.dilate(
        (all_mask | fills).astype(np.uint8), np.ones((CLEAN_DILATE * 2 + 1,) * 2, np.uint8)
    ).astype(bool)
    free = _free_space(gray, (left, top, right, bottom), background, cap_height)
    return Letters(
        glyphs=glyphs,
        light=light,
        ink=ink_level,
        background=background,
        uniform=uniform,
        mask=mask,
        expected=len(expected),
        extent=(float(left), top, float(right), bottom),
        cap_height=cap_height,
        free=free,
        word_gap=word_gap,
        gap=median_gap,
        paper=float(np.median(np.concatenate(paper_pixels))) if paper_pixels else None,
        hollow=by_bodies,
    )


def _free_space(
    gray: np.ndarray, extent: tuple[float, float, float, float], background: float, limit: float
) -> float:
    """Koliko se boja trake nastavlja iznad i ispod slova (manja od dve strane)."""
    left, top, right, bottom = (int(round(v)) for v in extent)
    height = gray.shape[0]

    def run(rows: range) -> int:
        count = 0
        for row in rows:
            line = gray[row, left:right].astype(np.float32)
            if not line.size or np.mean(np.abs(line - background) < TOLERANCE) < FREE_SHARE:
                break
            count += 1
        return count

    reach = int(limit)
    up = run(range(top - 1, max(top - reach, 0) - 1, -1))
    down = run(range(bottom, min(bottom + reach, height)))
    return float(min(up, down))


def max_scale(letters: Letters) -> float:
    """Koliko naslov sme da se uveća (popunjavanje širine) a da ne izađe iz trake."""
    _, top, _, bottom = letters.extent
    growth = 2 * GROWTH_USE * letters.free / max(1.0, bottom - top)
    return float(min(MAX_SCALE, 1 + growth))


# --- slova kojih nema u originalu -------------------------------------------------------------


def _canvas(char: str, font: ImageFont.FreeTypeFont) -> tuple[np.ndarray, int]:
    """Maska slova fonta na platnu 3× veličine slova, sa osnovnom linijom na 2/3 visine."""
    size = font.size
    canvas = Image.new("L", (size * 3, size * 3), 0)
    baseline = size * 2
    ImageDraw.Draw(canvas).text((size, baseline), char, font=font, fill=255, anchor="ls")
    return np.asarray(canvas) > 127, baseline


def _extent(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Redovi i kolone u kojima ima mastila."""
    return np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))


def _render(char: str, font: ImageFont.FreeTypeFont) -> tuple[np.ndarray, float] | None:
    """Maska slova fonta (sa marginom) i red osnovne linije u njoj."""
    mask, baseline = _canvas(char, font)
    rows, cols = _extent(mask)
    if not len(rows):
        return None
    margin = font.size // 3
    r0, r1 = max(rows[0] - margin, 0), rows[-1] + margin + 1
    c0, c1 = max(cols[0] - margin, 0), cols[-1] + margin + 1
    return mask[r0:r1, c0:c1], float(baseline - r0)


def _half_stroke(mask: np.ndarray) -> float:
    """Pola debljine poteza: 90. percentil udaljenosti od ivice unutar slova."""
    inside = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    values = inside[mask]
    return float(np.percentile(values, 90)) if values.size else 0.0


def _roughness(mask: np.ndarray, cap: float) -> float:
    """Srednje odstupanje ivice od zaglađenog oblika (px)."""
    smooth = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), SMOOTH * cap) > 0.5
    contours, _ = cv2.findContours(smooth.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
    return float(np.logical_xor(mask, smooth).sum() / max(perimeter, 1.0))


def _noise(shape: tuple[int, int], cap: float, seed: str) -> np.ndarray:
    rng = np.random.default_rng(zlib.crc32(seed.encode()))
    field_ = np.zeros(shape, np.float32)
    for weight, wave in WAVE:
        layer = cv2.GaussianBlur(rng.standard_normal(shape).astype(np.float32), (0, 0), wave * cap)
        field_ += weight * layer / max(float(layer.std()), 1e-6)
    return field_


@dataclass
class _Style:
    font: ImageFont.FreeTypeFont
    xscale: float
    delta: float  # promena polovine debljine poteza (px)
    amplitude: float  # jačina „raščupanosti" (px)
    cap: float
    slant: float = 0.0  # tangens nagiba
    outline: float = 0.0  # šuplja slova: debljina konture (px); 0 = puna slova


def _scaled(style: _Style, scale: int) -> _Style:
    """Isti stil, ali sve mere uvećane: slovo se crta krupno i tek na kraju smanjuje."""
    if scale == 1:
        return style
    return replace(
        style,
        font=ImageFont.truetype(style.font.path, style.font.size * scale),
        delta=style.delta * scale,
        amplitude=style.amplitude * scale,
        cap=style.cap * scale,
        outline=style.outline * scale,
    )


def _reduce(mask: np.ndarray, scale: int = SUPER) -> np.ndarray:
    """Uvećano slovo na pravoj veličini: ivica dobija prelaz kao na skenu, bez stepenica."""
    padded = np.pad(mask, ((0, -mask.shape[0] % scale), (0, -mask.shape[1] % scale)))
    size = (max(1, padded.shape[1] // scale), max(1, padded.shape[0] // scale))
    small = cv2.resize(padded.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    return (np.clip(cv2.GaussianBlur(small, (0, 0), SOFT_SIGMA), 0, 1) * 255).astype(np.uint8)


def _shape(char: str, style: _Style, seed: str) -> tuple[np.ndarray, float, np.ndarray] | None:
    """Slovo fonta prilagođeno slovima originala: širina, debljina poteza i hrapava ivica."""
    rendered = _render(char, style.font)
    if rendered is None:
        return None
    mask, baseline = rendered
    if style.xscale != 1:
        width = max(1, round(mask.shape[1] * style.xscale))
        mask = (
            cv2.resize(
                mask.astype(np.uint8), (width, mask.shape[0]), interpolation=cv2.INTER_LINEAR
            )
            > 0
        )
    mask = _shear(mask, style.slant, baseline)
    solid = _finish(mask, style, seed, outline=False)
    return _outline(solid, style), baseline, solid


def _finish(
    mask: np.ndarray, style: _Style, seed: str, share: float = 1.0, outline: bool = True
) -> np.ndarray:
    """Debljina poteza i „raščupana" ivica kao kod originala (share: blaže za sitne znakove)."""
    inside = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    outside = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)
    signed = inside - outside + style.delta * share
    if style.amplitude:
        signed = signed + style.amplitude * share * _noise(mask.shape, style.cap, seed)
    shaped = signed > 0
    # tanki šiljci od šuma (original ima zupce, ne dlačice)
    radius = max(1, round(HAIR * style.cap * share))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    shaped = cv2.morphologyEx(shaped.astype(np.uint8), cv2.MORPH_OPEN, kernel).astype(bool)
    shaped = _despeckle(shaped)
    return _outline(shaped, style) if outline else shaped


def _outline(shaped: np.ndarray, style: _Style) -> np.ndarray:
    """Šuplja slova: od punog oblika ostaje kontura iste debljine kao kod originala."""
    if not style.outline:
        return shaped
    size = 2 * max(1, round(style.outline)) + 1
    inner = cv2.erode(
        shaped.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    )
    ring = shaped & ~inner.astype(bool)
    return ring if ring.any() else shaped


def _despeckle(mask: np.ndarray) -> np.ndarray:
    """Ukloni ostrvca i rupice koje šum napravi uz ivicu (original ima zupce, ne prašinu)."""
    area = int(mask.sum())
    if not area:
        return mask
    result = mask.copy()
    for value, limit in zip((True, False), SPECK, strict=True):
        layer = (result == value).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(layer, connectivity=4)
        for i in range(1, count):
            if stats[i, cv2.CC_STAT_AREA] < limit * area:
                result[labels == i] = not value
    return result


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Slovo sa popunjenim unutrašnjim rupama (za šuplja slova: ceo oblik)."""
    padded = np.pad(mask, 1).astype(np.uint8)
    height, width = padded.shape
    cv2.floodFill(padded, np.zeros((height + 2, width + 2), np.uint8), (0, 0), 2)
    return (padded != 2)[1:-1, 1:-1]


def _shear(mask: np.ndarray, slant: float, base: float) -> np.ndarray:
    """Nakosi masku: red iznad osnovne linije pomera se udesno za `slant` po pikselu visine."""
    if not slant:
        return mask
    height = mask.shape[0]
    pad = int(np.ceil(abs(slant) * height)) + 1
    padded = np.pad(mask, ((0, 0), (pad, pad))).astype(np.uint8)
    matrix = np.float32([[1, -slant, slant * base], [0, 1, 0]])
    size = (padded.shape[1], height)
    return cv2.warpAffine(padded, matrix, size, flags=cv2.INTER_NEAREST) > 0


def _crop(mask: np.ndarray) -> np.ndarray:
    rows, cols = _extent(mask)
    return mask[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1] if len(rows) else mask


def _slant(masks: list[np.ndarray]) -> float:
    """Nagib slova (tangens): uspravni potezi daju najoštriji zbir mastila po stupcima."""
    tangents = np.tan(np.radians(np.arange(-MAX_SLANT, MAX_SLANT + 1)))

    def sharpness(mask: np.ndarray) -> float:
        column = mask.sum(axis=0).astype(float)
        return float((column**2).sum() / max(column.sum(), 1.0) ** 2)

    found = [
        max(tangents, key=lambda t, m=mask: sharpness(_shear(m, -t, m.shape[0]))) for mask in masks
    ]
    slant = float(np.median(found)) if found else 0.0
    return 0.0 if abs(slant) < np.tan(np.radians(MIN_SLANT)) else slant


def _tall(letters: Letters) -> list[Glyph]:
    """Slova originala pune visine (bez interpunkcije), na kojima se meri stil."""
    tall = []
    for glyph in letters.glyphs:
        rows, _ = _extent(glyph.alpha > 127)
        if glyph.char.isalpha() and len(rows) and rows[-1] - rows[0] >= 0.6 * letters.cap_height:
            tall.append(glyph)
    return tall


def _hollow(letters: Letters) -> bool:
    shares = []
    for glyph in _tall(letters):
        ink = glyph.alpha > 127
        shares.append(1 - ink.sum() / max(1, _fill_holes(ink).sum()))
    return bool(shares) and float(np.median(shares)) > HOLLOW


def _style(letters: Letters, font_path: Path, rough: bool = True) -> _Style:
    """Izmeri slova originala (širina, potez, nagib, kontura, hrapavost) i podesi font."""
    cap = letters.cap_height
    probe = ImageFont.truetype(str(font_path), 200)
    top = probe.getbbox("H", anchor="ls")[1]
    font = ImageFont.truetype(str(font_path), max(8, round(200 * cap / max(1.0, -top))))
    style = _Style(font=font, xscale=1.0, delta=0.0, amplitude=0.0, cap=cap)
    tall = _tall(letters)
    if not tall:
        return style
    raw = [glyph.alpha > 127 for glyph in tall]
    slant = _slant(raw)
    hollow = letters.hollow or _hollow(letters)

    def solid(glyph: Glyph, mask: np.ndarray) -> np.ndarray:
        """Celo slovo: kontura i unutrašnjost (ispuna je sigurnija od popunjavanja rupa konture)."""
        if glyph.fill is not None and glyph.fill.shape == mask.shape:
            return mask | (glyph.fill > 127)
        return _fill_holes(mask)

    # oblik se poredi uspravno i ispunjeno; kontura i nagib se dodaju na kraju
    shapes = [
        _crop(_shear(solid(glyph, m) if hollow else m, -slant, m.shape[0]))
        for glyph, m in zip(tall, raw, strict=True)
    ]
    ratios, originals, rendered = [], [], []
    for glyph, ink in zip(tall, shapes, strict=True):
        own = _render(glyph.char, font)
        if own is None:
            continue
        f_rows, f_cols = _extent(own[0])
        ratios.append((ink.shape[1] / ink.shape[0]) / ((np.ptp(f_cols) + 1) / (np.ptp(f_rows) + 1)))
        originals.append(ink)
        rendered.append(glyph.char)
    if not ratios:
        return style
    style.xscale = float(np.clip(np.median(ratios), 0.6, 2.0))
    original_stroke = float(np.median([_half_stroke(mask) for mask in originals]))
    plain = [_shape(char, style, char) for char in rendered]
    font_stroke = float(np.median([_half_stroke(shape[0]) for shape in plain if shape]))
    style.delta = original_stroke - font_stroke
    style.slant = slant
    if hollow:
        style.outline = 2 * float(np.median([_half_stroke(mask) for mask in raw]))
    if not rough:
        return style
    outline, style.outline = style.outline, 0.0  # hrapavost se meri na punom obliku
    samples = rendered[:3]

    def roughness() -> float:
        shapes = [_shape(char, style, char) for char in samples]
        return float(np.median([_roughness(_crop(shape[0]), cap) for shape in shapes if shape]))

    target = float(np.median([_roughness(mask, cap) for mask in originals]))
    # šuplja slova: izgled nosi kontura stalne debljine, a šum bi je izgužvao (spoljna ivica konture
    # preko crteža nosi i ostatke crteža, pa bi merenje ionako bilo pogrešno)
    if not hollow and target > ROUGH * roughness():  # glatka (štampana) slova ostaju glatka
        best = (float("inf"), 0.0)
        for amplitude in np.linspace(0, 0.12 * cap, 13)[1:]:
            style.amplitude = float(amplitude)
            best = min(best, (abs(roughness() - target), float(amplitude)))
        style.amplitude = best[1]
    style.outline = outline
    return style


def _similarity(letters: Letters, font_path: Path) -> float:
    """Koliko slova fonta, prilagođena originalu, liče na slova originala (poklapanje celog oblika).

    Poredi se ceo oblik slova (šuplje slovo sa unutrašnjošću), ne samo ivica: ivica kod šupljih
    slova ne razlikuje serife od pravih uglova, pa je serifni font umeo da pobedi zbijeni font bez
    serifa (štampani naslovi). Original se zaglađuje, da hrapava ivica ne odlučuje o izboru.
    """
    style = _style(letters, font_path, rough=False)
    scores = []
    for glyph in _tall(letters):
        shaped = _shape(glyph.char, style, glyph.char)
        if shaped is None:
            continue
        mask = glyph.alpha > 127
        if letters.hollow:
            mask = mask | (glyph.fill > 127) if glyph.fill is not None else _fill_holes(mask)
        smooth = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), SMOOTH * style.cap) > 0.5
        pair = [
            cv2.resize(_crop(m).astype(np.uint8) * 255, (64, 96), interpolation=cv2.INTER_AREA)
            > 127
            for m in (smooth, shaped[2])
        ]
        scores.append((pair[0] & pair[1]).sum() / max(1, (pair[0] | pair[1]).sum()))
    return float(np.mean(scores)) if scores else 0.0


def _glyph_from_mask(
    char: str,
    mask: np.ndarray,
    baseline: float,
    source: str,
    fill: np.ndarray | None = None,
    scale: int = 1,
) -> Glyph | None:
    """Slovo od maske; `scale` > 1 znači da je maska uvećana pa je treba smanjiti."""
    rows, cols = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    if not len(rows):
        return None
    pad = PAD * scale
    r0, r1 = max(rows[0] - pad, 0), min(rows[-1] + pad + 1, mask.shape[0])
    c0, c1 = max(cols[0] - pad, 0), min(cols[-1] + pad + 1, mask.shape[1])
    shrink = (lambda m: _reduce(m, scale)) if scale > 1 else _soft
    return Glyph(
        char=char,
        alpha=shrink(mask[r0:r1, c0:c1]),
        baseline=(baseline - r0) / scale,
        ink_left=float(cols[0] - c0) / scale,
        ink_right=float(cols[-1] + 1 - c0) / scale,
        source=source,
        fill=None if fill is None else shrink(fill[r0:r1, c0:c1]),
    )


def _soft(mask: np.ndarray) -> np.ndarray:
    return (np.clip(cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 0.7), 0, 1) * 255).astype(
        np.uint8
    )


def _accented(char: str, base: Glyph, style: _Style) -> Glyph | None:
    """Slovo originala sa dodatom kvačicom, akcentom ili crticom (S → Š, D → Đ).

    Znak je ono što slovo fonta sa znakom ima, a slovo bez znaka nema; prenosi se na slovo
    originala na isto mesto u odnosu na slovo, pa dobija debljinu i ivicu kao ostala slova.
    """
    big = _scaled(style, SUPER)  # znak se crta uvećan, pa smanjuje: ivica kao kod ostalih slova
    accented, _ = _canvas(char, big.font)
    plain, _ = _canvas(ACCENTED[char], big.font)
    ring = np.ones((5 * SUPER,) * 2, np.uint8)
    grown = cv2.dilate(plain.astype(np.uint8), ring).astype(bool)
    count, labels, stats, _ = cv2.connectedComponentsWithStats((accented & ~grown).astype(np.uint8))
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 0.01 * accented.sum()]
    p_rows, p_cols = _extent(plain)
    b_rows, b_cols = _extent(base.alpha > 127)
    if not keep or not len(p_rows) or not len(b_rows):
        return None
    mark = np.isin(labels, keep)
    # font je uvećan SUPER puta, original nije: sx vodi iz platna fonta u uvećano slovo originala
    sx = SUPER * (b_cols[-1] - b_cols[0] + 1) / (p_cols[-1] - p_cols[0] + 1)
    height, width = base.alpha.shape
    if char == "Đ":
        # crtica preko stabla: preslikava se sa D fonta na D originala
        sy = SUPER * (b_rows[-1] - b_rows[0] + 1) / (p_rows[-1] - p_rows[0] + 1)
        matrix = np.float32(
            [
                [sx, 0, SUPER * b_cols[0] - p_cols[0] * sx],
                [0, sy, SUPER * b_rows[0] - p_rows[0] * sy],
            ]
        )
        placed = (
            cv2.warpAffine(
                mark.astype(np.uint8),
                matrix,
                (width * SUPER, height * SUPER),
                flags=cv2.INTER_NEAREST,
            )
            > 0
        )
        bar = _finish(placed, big, char, share=0.5)
        alpha = np.maximum(base.alpha, _reduce(bar))
        fill = None
        if base.fill is not None:
            fill = np.maximum(base.fill, _reduce(_finish(placed, big, char, 0.5, outline=False)))
        return Glyph(
            char, alpha, base.baseline, base.ink_left, base.ink_right, source="accent", fill=fill
        )
    # kvačica ili akcenat iznad slova
    m_rows, m_cols = _extent(mark)
    piece = mark[m_rows[0] : m_rows[-1] + 1, m_cols[0] : m_cols[-1] + 1].astype(np.uint8)
    piece_width = max(1, round(piece.shape[1] * style.xscale))
    piece = cv2.resize(piece, (piece_width, piece.shape[0]), interpolation=cv2.INTER_LINEAR) > 0
    piece = _shear(piece, style.slant, piece.shape[0])
    margin = max(4 * SUPER, int(0.1 * big.cap))
    solid = _finish(np.pad(piece, margin), big, char, 0.5, outline=False)
    piece = _outline(solid, big)
    rows, cols = _extent(solid)
    if not len(rows):
        return None
    piece = _reduce(piece[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1])
    solid = _reduce(solid[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1])
    # sredina znaka u odnosu na sredinu slova fonta, preračunata na širinu slova originala
    offset = ((m_cols[0] + m_cols[-1] + 1) / 2 - (p_cols[0] + p_cols[-1] + 1) / 2) * sx / SUPER
    center = (b_cols[0] + b_cols[-1] + 1) / 2 + offset
    gap = (p_rows[0] - (m_rows[-1] + 1)) * MARK_GAP / SUPER
    mark_top = b_rows[0] - gap - piece.shape[0]
    # koso slovo: znak iznad slova je pomeren udesno koliko i vrh slova
    center += style.slant * ((b_rows[0] + base.baseline) / 2 - (mark_top + piece.shape[0] / 2))
    mark_left = center - piece.shape[1] / 2
    extra_top = max(0, int(np.ceil(-mark_top)) + PAD)
    left_pad = max(0, int(np.ceil(-mark_left)) + PAD)
    right_pad = max(0, int(np.ceil(mark_left + piece.shape[1] - width)) + PAD)
    alpha = np.zeros((height + extra_top, width + left_pad + right_pad), np.uint8)
    alpha[extra_top:, left_pad : left_pad + width] = base.alpha
    top, left = int(round(mark_top)) + extra_top, int(round(mark_left)) + left_pad
    region = alpha[top : top + piece.shape[0], left : left + piece.shape[1]]
    np.maximum(region, piece[: region.shape[0], : region.shape[1]], out=region)
    fill = None
    if base.fill is not None:  # šuplje slovo: i znak dobija ispunu
        fill = np.zeros_like(alpha)
        fill[extra_top:, left_pad : left_pad + width] = base.fill
        region = fill[top : top + solid.shape[0], left : left + solid.shape[1]]
        np.maximum(region, solid[: region.shape[0], : region.shape[1]], out=region)
    return Glyph(
        char,
        alpha,
        base.baseline + extra_top,
        base.ink_left + left_pad,
        base.ink_right + left_pad,
        source="accent",
        fill=fill,
    )


def complete(
    letters: Letters,
    fonts: tuple[tuple[str, Path], ...] = FONTS,
    chosen: dict[str, str] | None = None,
    manual: tuple[tuple[str, Path], ...] = (),
) -> None:
    """Dopuni slova koja u originalu nedostaju (letters.extra), fontom najsličnijim originalu.

    `chosen` je ručni izbor fonta po slovu (K → „Anton"); takvo slovo se pravi od tog fonta, i
    kad bi se inače dobilo dodavanjem kvačice na slovo originala. `manual` su fontovi koji se
    nude samo za ručni izbor (npr. rukopis za dijalog), a automatski izbor ih ne razmatra.
    """
    present = {g.char for g in letters.glyphs}
    missing = [char for char in CHARSET if char not in present]
    letters.slant = _slant([glyph.alpha > 127 for glyph in _tall(letters)])
    letters.hollow = letters.hollow or _hollow(letters)
    letters.fonts = [font_name for font_name, _ in fonts + manual]
    if not missing:
        return
    name, path = (
        max(fonts, key=lambda font: _similarity(letters, font[1])) if len(fonts) > 1 else fonts[0]
    )
    letters.font = name
    paths = dict(fonts + manual)
    styles: dict[str, tuple[_Style, _Style]] = {}

    def styled(font_name: str) -> tuple[_Style, _Style]:
        if font_name not in styles:
            own = _style(letters, paths[font_name])
            styles[font_name] = (own, _scaled(own, SUPER))
        return styles[font_name]

    extra = []
    for char in missing:
        own = (chosen or {}).get(char)
        font_name = own if own in paths else name
        style, big = styled(font_name)
        base = ACCENTED.get(char)
        if base in present and own not in paths:
            source = next(g for g in letters.glyphs if g.char == base)
            glyph = _accented(char, source, style)
            if glyph is not None:
                extra.append(glyph)
                continue
        shaped = _shape(char, big, char)
        if shaped is None:
            continue
        solid = shaped[2] if style.outline else None
        glyph = _glyph_from_mask(char, shaped[0], shaped[1], "fallback", fill=solid, scale=SUPER)
        if glyph is not None:
            glyph.font = font_name
            extra.append(glyph)
    letters.extra = extra


# --- čuvanje ----------------------------------------------------------------------------------


def _paper(letters: Letters) -> float:
    """Boja ispune: papir iz unutrašnjosti slova, inače suprotno od mastila."""
    return letters.paper if letters.paper is not None else (0.0 if letters.light else 255.0)


def _write(alpha: np.ndarray, level: float, path: Path) -> None:
    luminance = np.full(alpha.shape, int(round(level)), np.uint8)
    Image.fromarray(np.dstack([luminance, alpha]), "LA").save(path, optimize=True)


def _png(glyph: Glyph, ink: float, path: Path, paper: float | None = None) -> None:
    """Slika slova (boja mastila) i, ako je ima, ispuna u susednom fajlu {ključ}f.png."""
    _write(glyph.alpha, ink, path)
    if glyph.fill is not None and paper is not None:
        _write(glyph.fill, paper, path.with_name(f"{path.stem}f.png"))


def describe(letters: Letters, text: str, box: Box, version: str) -> dict:
    """Opis skupa slova za bazu (text_blocks.title) i frontend."""

    def entry(key: str, glyph: Glyph) -> dict:
        height, width = glyph.alpha.shape
        data = {
            "key": key,
            "char": glyph.char,
            "source": glyph.source,
            "width": width,
            "height": height,
            "baseline": round(glyph.baseline, 2),
            "ink_left": float(glyph.ink_left),
            "ink_right": float(glyph.ink_right),
            "fill": glyph.fill is not None,
        }
        if glyph.font:
            data["font"] = glyph.font
        if glyph.box is not None:
            data |= {
                "x": glyph.box[0],
                "y": glyph.box[1],
                "row": glyph.row,
                "space_before": glyph.space_before,
                "gap_next": glyph.gap_next,
            }
        return data

    left, top, right, bottom = letters.extent
    return {
        "version": version,
        "text": text,
        "box": [float(value) for value in box],
        "light": letters.light,
        "ink": round(letters.ink),
        "paper": round(_paper(letters)),
        "background": round(letters.background),
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "cap_height": round(letters.cap_height, 2),
        "max_scale": round(max_scale(letters), 3),
        "gap": round(letters.gap, 2),
        "word_gap": round(letters.word_gap, 2),
        "font": letters.font,
        "fonts": letters.fonts,
        "slant": round(float(np.degrees(np.arctan(letters.slant))), 1),
        "hollow": letters.hollow,
        "angle": round(letters.angle, 2),
        "skew": round(letters.skew, 4),
        "center": [round(value, 1) for value in letters.center] if letters.center else None,
        "found": len(letters.glyphs),
        "expected": letters.expected,
        "glyphs": [entry(f"g{i}", g) for i, g in enumerate(letters.glyphs)],
        "extra": [entry(f"x{i}", g) for i, g in enumerate(letters.extra)],
    }


def title_dir(data_dir: Path, project_id: int, block_id: int) -> Path:
    return data_dir / "projects" / str(project_id) / "titles" / str(block_id)


def sweep(data_dir: Path, project_id: int, keep: set[int]) -> None:
    """Obriši slova blokova kojih više nema (obrisana stranica); `keep` su postojeći blokovi."""
    root = title_dir(data_dir, project_id, 0).parent
    if not root.is_dir():
        return
    for folder in root.iterdir():
        if folder.is_dir() and (not folder.name.isdigit() or int(folder.name) not in keep):
            shutil.rmtree(folder, ignore_errors=True)


def save(letters: Letters, text: str, box: Box, target: Path, previous: dict | None = None) -> dict:
    """Snimi slike slova u novu verziju (stare se brišu) i vrati opis.

    Slova sastavljena od delova (6b) prelaze iz prethodne verzije neizmenjena.
    """
    version = uuid.uuid4().hex[:12]
    folder = target / version
    folder.mkdir(parents=True, exist_ok=True)
    for i, glyph in enumerate(letters.glyphs):
        _png(glyph, letters.ink, folder / f"g{i}.png", _paper(letters))
    for i, glyph in enumerate(letters.extra):
        _png(glyph, letters.ink, folder / f"x{i}.png", _paper(letters))
    custom = []
    for entry in (previous or {}).get("custom", []):
        source = target / previous["version"] / f"{entry['key']}.png"
        if source.exists():
            shutil.copyfile(source, folder / source.name)
            fill = source.with_name(f"{entry['key']}f.png")
            if fill.exists():
                shutil.copyfile(fill, folder / fill.name)
            custom.append(entry)
    # starije verzije ostaju zbog „Poništi"; najstarije se brišu
    others = sorted(
        (item for item in target.iterdir() if item.is_dir() and item.name != version),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old in others[VERSIONS - 1 :]:
        shutil.rmtree(old, ignore_errors=True)
    return describe(letters, text, box, version) | {"custom": custom}


def version_exists(block: TextBlock, data_dir: Path) -> bool:
    """Da li slike slova opisane verzije još postoje (posle „Poništi" mogu da fale)."""
    if not block.title:
        return True
    folder = title_dir(data_dir, block.page.project_id, block.id) / block.title["version"]
    return folder.is_dir()


def title_fonts(
    block: TextBlock, data_dir: Path, kinds: tuple[str, ...] = ("title",)
) -> tuple[tuple[str, Path], ...]:
    """Korisnički fontovi za naslove (npr. napravljeni od naslova srpskog izdanja)."""
    session = object_session(block)
    if session is None:
        return ()
    fonts = session.scalars(select(Font).where(Font.kind.in_(kinds)).order_by(Font.id))
    return tuple(
        (font.name, data_dir / font.path) for font in fonts if (data_dir / font.path).exists()
    )


def refresh(block: TextBlock, data_dir: Path, gray: np.ndarray | None = None) -> Letters | None:
    """Iseci slova naslova bloka iz originala, dopuni ih i upiši opis u block.title."""
    page = block.page
    if gray is None:
        with Image.open(data_dir / page.image_path) as image:
            gray = np.asarray(image.convert("L"))
    box = (block.x, block.y, block.width, block.height)
    target = title_dir(data_dir, page.project_id, block.id)
    letters = find_letters(gray, box, block.text)
    if letters is None:
        shutil.rmtree(target, ignore_errors=True)
        block.title = None
        return None
    chosen = (block.style or {}).get("letter_fonts") or {}
    # rukopis za dijalog i onomatopeje: samo za ručni izbor slova (npr. natpis u rukopisu)
    manual = title_fonts(block, data_dir, ("dialogue", "sfx"))
    complete(letters, FONTS + title_fonts(block, data_dir), chosen, manual)
    block.title = save(letters, block.text, box, target, previous=block.title)
    return letters


def _entries(title: dict) -> list[dict]:
    return title["glyphs"] + title["extra"] + title.get("custom", [])


def glyph_file(data_dir: Path, block: TextBlock, key: str) -> Path | None:
    """Slika jednog slova naslova (ključ iz opisa: g0… original, x0… dopunjeno, c0… sastavljeno)."""
    if not GLYPH_KEY.fullmatch(key):
        return None
    entries = {entry["key"]: entry for entry in _entries(block.title)} if block.title else {}
    base = key[:-1] if key.endswith("f") else key  # g3f: ispuna slova g3
    if base not in entries or (base != key and not entries[base].get("fill")):
        return None
    folder = title_dir(data_dir, block.page.project_id, block.id) / block.title["version"]
    path = inside(folder, f"{key}.png")
    return path if path.exists() else None


class GlyphError(ValueError):
    """Neispravno slovo sastavljeno od delova."""


# oznaka slova u adresi: g0… original, x0… dopunjeno, c0… sastavljeno; „f" na kraju je ispuna
GLYPH_KEY = re.compile(r"[gxc]\d{1,4}f?")


MAX_GLYPH = 2000  # px, najveća slika sastavljenog slova


def save_custom(
    block: TextBlock,
    data_dir: Path,
    data: bytes,
    char: str,
    baseline: float,
    parts: list,
    key: str | None = None,
    fill: bytes | None = None,
) -> str:
    """Snimi slovo sastavljeno od delova (6b); `key` zamenjuje postojeće. Vraća ključ slova.

    `fill` je ispuna (unutrašnjost šupljih slova), iste veličine kao slovo.
    """
    if not block.title:
        raise GlyphError("naslov nema isečena slova")
    char = char.strip().upper()
    if len(char) != 1 or char.isspace():
        raise GlyphError("slovo mora biti jedan znak")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            alpha = np.asarray(image.convert("RGBA"))[..., 3]
    except (OSError, SyntaxError) as exc:
        raise GlyphError("slika slova nije ispravna") from exc
    height, width = alpha.shape
    if width > MAX_GLYPH or height > MAX_GLYPH:
        raise GlyphError("slika slova je prevelika")
    rows, cols = _extent(alpha > 127)
    if not len(rows):
        raise GlyphError("slovo je prazno")
    fill_alpha = None
    if fill is not None:
        try:
            with Image.open(io.BytesIO(fill)) as image:
                fill_alpha = np.asarray(image.convert("RGBA"))[..., 3]
        except (OSError, SyntaxError) as exc:
            raise GlyphError("slika ispune nije ispravna") from exc
        if fill_alpha.shape != alpha.shape:
            raise GlyphError("ispuna mora biti iste veličine kao slovo")
    custom = [dict(entry) for entry in block.title.get("custom", [])]
    keys = [entry["key"] for entry in custom]
    if key is not None and (key not in keys or not GLYPH_KEY.fullmatch(key)):
        raise GlyphError("sastavljeno slovo ne postoji")
    if key is None:
        key = f"c{max((int(k[1:]) for k in keys), default=-1) + 1}"
    glyph = Glyph(
        char, alpha, float(baseline), float(cols[0]), float(cols[-1] + 1), "custom", fill=fill_alpha
    )
    folder = title_dir(data_dir, block.page.project_id, block.id) / block.title["version"]
    inside(folder, f"{key}f.png").unlink(missing_ok=True)
    _png(glyph, block.title["ink"], inside(folder, f"{key}.png"), block.title.get("paper"))
    entry = {
        "key": key,
        "char": char,
        "source": "custom",
        "width": width,
        "height": height,
        "baseline": round(float(baseline), 2),
        "ink_left": glyph.ink_left,
        "ink_right": glyph.ink_right,
        "fill": fill_alpha is not None,
        "parts": parts,
    }
    custom = [entry if item["key"] == key else item for item in custom]
    if key not in keys:
        custom.append(entry)
    block.title = {**block.title, "custom": custom}  # nov rečnik: SQLAlchemy vidi izmenu
    return key


def remove_custom(block: TextBlock, data_dir: Path, key: str) -> None:
    custom = [entry for entry in (block.title or {}).get("custom", []) if entry["key"] != key]
    missing = not block.title or len(custom) == len(block.title.get("custom", []))
    if missing or not GLYPH_KEY.fullmatch(key):
        raise GlyphError("sastavljeno slovo ne postoji")
    folder = title_dir(data_dir, block.page.project_id, block.id) / block.title["version"]
    inside(folder, f"{key}.png").unlink(missing_ok=True)
    inside(folder, f"{key}f.png").unlink(missing_ok=True)
    block.title = {**block.title, "custom": custom}
