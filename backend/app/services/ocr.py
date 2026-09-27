"""OCR tekst bloka preko vision modela na llama-serveru."""

import io
import re
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.models import TextBlock
from app.services.llamaserver import LlamaServerClient

CROP_MARGIN = 0.1  # deo veličine bloka koji se dodaje sa svake strane
CROP_MIN_MARGIN = 12  # piksela
MIN_CROP_HEIGHT = 200  # niži isečci se uvećavaju, sitna slova se tako bolje čitaju
MAX_UPSCALE = 3

LANGUAGES = {"it": "Italian", "sr": "Serbian (Latin script)"}
DEFAULT_PROMPT = (
    "Transcribe the text in this image exactly as written. The image is a crop of a comic book "
    "page in {language} (speech balloon, caption or sound effect) with uppercase hand lettering. "
    "Keep the original line breaks and the hyphens at the end of lines. Do not translate, "
    "explain or add anything. If there is no text, reply with an empty message."
)

FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
LABEL = re.compile(r"^(text|testo|transcription|ocr)\s*:\s*", re.IGNORECASE)
QUOTES = {'"': '"', "“": "”", "«": "»"}
LAST_LATIN_CODEPOINT = 0x024F
MAX_LOWERCASE_SHARE = 0.3


@dataclass
class OcrResult:
    text: str
    model: str
    seconds: float
    needs_review: bool


def prompt_for(language: str = "it") -> str:
    return DEFAULT_PROMPT.format(language=LANGUAGES.get(language, "Italian"))


def crop_block(image_path: Path, x: float, y: float, width: float, height: float) -> bytes:
    """PNG isečak bloka sa marginom, uvećan ako je nizak."""
    with Image.open(image_path) as image:
        margin_x = max(CROP_MIN_MARGIN, width * CROP_MARGIN)
        margin_y = max(CROP_MIN_MARGIN, height * CROP_MARGIN)
        box = (
            max(0, round(x - margin_x)),
            max(0, round(y - margin_y)),
            min(image.width, round(x + width + margin_x)),
            min(image.height, round(y + height + margin_y)),
        )
        crop = image.crop(box)
    if crop.mode not in ("L", "RGB"):
        crop = crop.convert("RGB")
    if crop.height < MIN_CROP_HEIGHT:
        factor = min(MAX_UPSCALE, MIN_CROP_HEIGHT / crop.height)
        size = (round(crop.width * factor), round(crop.height * factor))
        crop = crop.resize(size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    crop.save(buffer, "PNG")
    return buffer.getvalue()


def clean_output(raw: str) -> str:
    """Ukloni ukrase koje modeli dodaju: markdown ograde, „Text:", navodnike, prazne redove."""
    text = FENCE.sub("", raw.strip())
    text = LABEL.sub("", text.strip())
    if len(text) >= 2 and QUOTES.get(text[0]) == text[-1]:
        text = text[1:-1]
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


# ispravke za sve modele, nađene u benchmarku Faze 2 (docs/benchmarks/faza2.md)
COMMON_FIXES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<=[A-ZÀ-Ý])- (?=[A-ZÀ-Ý])"), "-\n"),  # „IMMEDIA- TI" → prelom reda
    (re.compile(r"·"), "'"),  # „E·LUI" → „E'LUI"
    (re.compile(r"''"), "'"),
    (re.compile(r"!/"), "!"),  # „RAMON!/..." → „RAMON!..."
    (re.compile(r"\s+/(?=\.{2,})"), "!"),  # „TOD /..." → „TOD!..."
]


def fix_punctuation(text: str) -> str:
    for pattern, replacement in COMMON_FIXES:
        text = pattern.sub(replacement, text)
    return text


def _lowercase_share(text: str) -> float | None:
    letters = [char for char in text if char.isalpha()]
    return sum(char.islower() for char in letters) / len(letters) if letters else None


def uppercase_lettering(text: str) -> str:
    """Ručni lettering je samo velikim slovima: pretežno velika slova se prevode u sva velika."""
    share = _lowercase_share(text)
    return text.upper() if share is not None and share <= MAX_LOWERCASE_SHARE else text


def needs_review(text: str) -> bool:
    """Sumnjiv rezultat: bez slova, pretežno mala slova (lettering je velikim) ili nelatinica."""
    share = _lowercase_share(text)
    if share is None:
        return True
    non_latin = any(ord(char) > LAST_LATIN_CODEPOINT for char in text if char.isalpha())
    return share > MAX_LOWERCASE_SHARE or non_latin or len(text) > 500


# Petlje modela: u pravim onomatopejama (izmereno na ~150) isto slovo se ponavlja najviše ~7 puta, a
# obrazac od više slova najviše ~2 puta; duže je model „zaglavio" („SSSSSS…", „MAMAMA…").
LONG_RUN = re.compile(r"(.)\1{8,}")  # isti znak više od 8 puta → 4
LONG_PATTERN = re.compile(
    r"(..{1,3}?)\1{6,}"
)  # obrazac od 2–4 znaka više od 6 puta → 3 ponavljanja
STYLED_KINDS = {"sfx", "title", "other"}
SFX_MAX_TOKENS = 60  # onomatopeja je kratka: dug odgovor je petlja ili izmišljen tekst


def tame_repeats(text: str) -> tuple[str, bool]:
    """Skrati ponavljanja kakva nastaju kad se model zaglavi; vraća i da li je nešto skraćeno."""
    tamed = LONG_RUN.sub(lambda m: m.group(1) * 4, text)
    tamed = LONG_PATTERN.sub(lambda m: m.group(1) * 3, tamed)
    return tamed, tamed != text


def postprocess(raw: str, kind: str) -> tuple[str, bool]:
    """Tekst odgovora modela za blok; drugi deo kaže da je odgovor sumnjiv (skraćena petlja)."""
    text, looped = tame_repeats(fix_punctuation(clean_output(raw)))
    if kind in STYLED_KINDS and not any(char.isalpha() for char in text):
        text = ""  # bar-kod, brojevi, crtice: lažna detekcija natpisa, a ne tekst
    return uppercase_lettering(text), looped


def max_tokens_for(kind: str, max_tokens: int) -> int:
    return min(max_tokens, SFX_MAX_TOKENS) if kind == "sfx" else max_tokens


def read_block(
    client: LlamaServerClient,
    image_path: Path,
    block: TextBlock,
    model: str,
    max_tokens: int,
    language: str = "it",
) -> OcrResult:
    crop = crop_block(image_path, block.x, block.y, block.width, block.height)
    started = time.monotonic()
    tokens = max_tokens_for(block.kind, max_tokens)
    result = client.generate(prompt_for(language), model, tokens, images=[crop], temperature=0)
    text, looped = postprocess(result.response, block.kind)
    return OcrResult(
        text=text,
        model=model,
        seconds=round(time.monotonic() - started, 2),
        needs_review=looped or needs_review(text),
    )
