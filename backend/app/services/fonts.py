"""Fontovi za slaganje prevoda: ugrađeni (OFL) i korisnički, uz proveru srpskih slova.

Provera gleda i da li slovo zaista ima crtež: neki fontovi (Laffayette Comic Pro, Blam Blam BB)
navode Č Ć Ž Š Đ u tabeli znakova, a glif je prazan.
"""

import io
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont, TTLibError
from sqlalchemy.orm import Session

from app.models import Font

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "fonts"
# strip se slaže velikim slovima, pa mala slova nisu obavezna (mnogi strip fontovi ih nemaju);
# crtica je obavezna zbog rastavljanja reči na kraju reda
REQUIRED = "ABCČĆDĐEFGHIJKLMNOPRSŠTUVZŽ!?.,-"


@dataclass(frozen=True)
class BuiltinFont:
    key: str
    name: str
    filename: str
    kind: str  # dialogue | sfx


BUILTIN = (
    BuiltinFont("comic-neue-bold", "Comic Neue Bold", "ComicNeue-Bold.ttf", "dialogue"),
    BuiltinFont(
        "shantell-sans", "Shantell Sans (neformalni)", "ShantellSans-Informal.ttf", "dialogue"
    ),
    BuiltinFont("patrick-hand-sc", "Patrick Hand SC", "PatrickHandSC-Regular.ttf", "dialogue"),
    BuiltinFont("balsamiq-sans-bold", "Balsamiq Sans Bold", "BalsamiqSans-Bold.ttf", "dialogue"),
    BuiltinFont("bangers", "Bangers", "Bangers-Regular.ttf", "sfx"),
)
DEFAULT_DIALOGUE = "comic-neue-bold"
DEFAULT_SFX = "bangers"


class FontRejected(ValueError):
    """Fajl nije font ili mu fale srpska slova."""


def _has_outline(font: TTFont, glyph_name: str) -> bool:
    glyphs = font.getGlyphSet()
    pen = BoundsPen(glyphs)
    glyphs[glyph_name].draw(pen)
    return pen.bounds is not None


def inspect_font(data: bytes) -> tuple[str, list[str]]:
    """Ime porodice fonta i slova koja fale (nema ih u tabeli ili je glif prazan)."""
    try:
        font = TTFont(io.BytesIO(data), lazy=True)
        cmap = font.getBestCmap() or {}
        name = font["name"].getBestFullName() or font["name"].getBestFamilyName() or "font"
    except (TTLibError, KeyError, AssertionError, ValueError, OSError) as exc:
        raise FontRejected("fajl nije TTF ili OTF font") from exc
    missing = []
    for char in REQUIRED:
        glyph = cmap.get(ord(char))
        if glyph is None or not _has_outline(font, glyph):
            missing.append(char)
    return str(name), missing


USER_PREFIX = "user-"


def builtin(key: str) -> BuiltinFont | None:
    return next((font for font in BUILTIN if font.key == key), None)


def user_font(session: Session, key: str) -> Font | None:
    if not key.startswith(USER_PREFIX) or not key.removeprefix(USER_PREFIX).isdigit():
        return None
    return session.get(Font, int(key.removeprefix(USER_PREFIX)))


def font_exists(session: Session, key: str) -> bool:
    return builtin(key) is not None or user_font(session, key) is not None
