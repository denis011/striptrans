"""Provera pravopisa prevoda: hunspell sr_Latn_RS preko spylls, lokalno i bez mreže."""

import re
from functools import lru_cache

DICTIONARY = "/usr/share/hunspell/sr_Latn_RS"
LETTERS = "A-Za-zČĆŽŠĐčćžšđ"
WORD = re.compile(rf"[{LETTERS}]+(?:['’\-][{LETTERS}]+)*")


@lru_cache(maxsize=1)
def _dictionary():
    """Učitavanje traje par sekundi, pa se rečnik drži u memoriji procesa."""
    from spylls.hunspell import Dictionary

    return Dictionary.from_files(DICTIONARY)


def words(text: str) -> list[str]:
    return WORD.findall(text)


@lru_cache(maxsize=20000)
def _known(word: str) -> bool:
    return _dictionary().lookup(word)


def unknown_words(text: str, allowed: frozenset[str] = frozenset()) -> list[str]:
    """Reči kojih nema u rečniku ni među dozvoljenim (glosar, rečnik), bez ponavljanja."""
    found: list[str] = []
    for word in words(text):
        lowered = word.lower()
        if lowered in allowed or lowered in (w.lower() for w in found):
            continue
        if not _known(lowered) and not _known(word):
            found.append(word)
    return found


def allowed_words(*sources: str) -> frozenset[str]:
    """Sve reči iz glosara i korisnikovog rečnika, u malim slovima."""
    return frozenset(word.lower() for source in sources for word in words(source))


# hrvatske i ijekavske reči koje ne pripadaju srpskom (ekavskom) prevodu: cele reči i početci reči
NON_SERBIAN_WORDS = {"TKO", "NETKO", "NITKO", "SVATKO", "PRIJE"}  # PRIJEM je srpski
NON_SERBIAN = (
    "TISUĆ", "TOČN", "TJED", "KRUH", "VLAK", "OBITELJ", "ZRAKOPLOV",
    "UVIJEK", "VRIJEM", "RIJEČ", "DJEVOJ", "LIJEP", "BIJEL", "CIJEL", "MJEST", "DJEC", "SVIJET",
    "VIJEST", "POSLIJE", "OVDJE", "GDJE", "ONDJE", "NIGDJE", "NEGDJE", "SJEĆ", "RIJEK",
    "ČOVJEK", "TIJEL", "PJESM", "MLIJEK", "DIJET", "SNIJEG", "MJESEC", "ŽELJEZ", "SJEDI", "VJER",
)  # fmt: skip


def non_serbian_words(text: str) -> list[str]:
    """Reči prevoda koje su hrvatske ili ijekavske (npr. TISUĆU, TKO, UVIJEK), bez ponavljanja.

    Rečnik sr_Latn_RS ih prihvata (ima i ijekavske oblike), pa ih pravopis ne označava.
    """
    found: list[str] = []
    for word in re.findall(r"[A-ZČĆŽŠĐ]+", text.upper()):
        if (word in NON_SERBIAN_WORDS or word.startswith(NON_SERBIAN)) and word not in found:
            found.append(word)
    return found
