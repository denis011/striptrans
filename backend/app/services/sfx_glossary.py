"""Onomatopeje se ne prevode modelom: prvo glosar onomatopeja, pa pravilo.

Pravilo (odluka korisnika 2026-09-27): reč sa SH ili W se prilagođava srpskom izgovoru
(CRASH → KRAŠ, SVISH → SVIŠ), sve ostale ostaju kako jesu (BANG, ZING, FLAP).
"""

import re
from collections import Counter
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Page, Project, Series, SfxEntry, TextBlock
from app.services import history
from app.services.glossary_suggest import flatten
from app.services.translation import is_too_long

MODEL = "onomatopeje"
WORD = re.compile(r"[^\W\d_]+")
EDGES = re.compile(r"^\W+|\W+$")  # znaci na krajevima; uzimaju se iz originala
# redosled je bitan: dvoslovi pre pojedinačnih slova
ADAPT = [
    ("CH", "Č"),
    ("CK", "K"),
    ("WH", "V"),
    ("PH", "F"),
    ("TH", "T"),
    ("C", "K"),
    ("Q", "K"),
    ("X", "KS"),
    ("W", "V"),
    ("Y", "J"),
]


def key(text: str) -> str:
    """Ključ glosara: samo slova i brojevi, velikim slovima (WOAH! i WOAH su isto)."""
    return " ".join(re.findall(r"[^\W\d_]+|\d+", text.upper()))


def adapt(word: str) -> str:
    """Reč sa SH ili W po izgovoru; ostale reči ostaju iste."""
    word = word.upper()
    if "SH" not in word and "W" not in word:
        return word
    word = re.sub(r"SH+", lambda match: "Š" * (len(match.group(0)) - 1), word)  # SHHH → ŠŠŠ
    for old, new in ADAPT:
        word = word.replace(old, new)
    return word


def load(session: Session) -> dict[str, str]:
    return {entry.source: entry.target for entry in session.scalars(select(SfxEntry))}


VOWELS = set("AEIOU")


def _runs(word: str) -> list[tuple[str, int]]:
    return [(letter, len(list(group))) for letter, group in groupby(word)]


def collapse(word: str) -> str:
    """Reč bez produženih slova: CRAAASH → CRASH, SHHH → SH."""
    return "".join(letter for letter, _ in _runs(word))


def stretch(word: str, source: str, target: str) -> str:
    """Produženje iz originala prenosi se na zapis iz glosara: CRAAASH uz CRASH → KRAŠ daje KRAAAŠ.

    Produžen samoglasnik produžava isti po redu samoglasnik zapisa, a produženo poslednje slovo
    poslednje slovo zapisa (CRASHHH → KRAŠŠŠ); ostala produženja se ne prenose.
    """
    have, base = _runs(word), _runs(source)
    out = [[letter, count] for letter, count in _runs(target)]
    vowel_runs = [run for run in out if run[0] in VOWELS]
    for index, ((letter, count), (_, base_count)) in enumerate(zip(have, base, strict=True)):
        extra = count - base_count
        if extra <= 0 or not out:
            continue
        if letter in VOWELS:
            order = sum(run[0] in VOWELS for run in base[:index])
            if order < len(vowel_runs):
                vowel_runs[order][1] += extra
        elif index == len(have) - 1:
            out[-1][1] += extra
    return "".join(letter * count for letter, count in out)


def lookup(word: str, glossary: dict[str, str]) -> tuple[str | None, bool]:
    """Zapis iz glosara za jednu reč i da li je nađen preko produženog oblika (CRAAASH → CRASH)."""
    if word in glossary:
        return EDGES.sub("", glossary[word]), False
    for source, target in glossary.items():
        if " " not in source and collapse(source) == collapse(word):
            return stretch(word, source, EDGES.sub("", target)), True
    return None, False


def translate(text: str, glossary: dict[str, str]) -> str:
    """Više reči tačno iz glosara (AH! AH! AH!), inače svaka reč posebno: glosar pa pravilo.

    Kod pojedinačnih reči znaci ostaju iz originala (SWACK!! → SCVAK!!).
    """
    text = text.upper()
    if " " in key(text) and key(text) in glossary:
        return glossary[key(text)]

    def word(match: re.Match) -> str:
        found, _ = lookup(match.group(0), glossary)
        return found if found is not None else adapt(match.group(0))

    return WORD.sub(word, text)


def proposals(text: str, glossary: dict[str, str]) -> list[tuple[str, str]]:
    """Reči koje čekaju potvrdu: promenjene po pravilu (SH, W) ili produžene (CRAAASH)."""
    text = text.upper()
    if " " in key(text) and key(text) in glossary:
        return []
    found = {}
    for word in WORD.findall(text):
        target, stretched = lookup(word, glossary)
        if target is None and adapt(word) != word:
            found[word] = adapt(word)
        elif stretched:
            found[word] = target
    return list(found.items())


def apply(block: TextBlock, glossary: dict[str, str]) -> None:
    source = flatten(block.text)
    block.translation = translate(source, glossary)
    block.translation_model = MODEL
    block.translation_status = "draft"
    block.translation_too_long = is_too_long(source, block.translation)


def missing(session: Session) -> list[dict]:
    """Reči onomatopeja iz originala za prevod koje nisu u glosaru, sa predlogom po pravilu."""
    glossary = load(session)
    query = (
        select(TextBlock.text)
        .join(Page, TextBlock.page_id == Page.id)
        .join(Project, Page.project_id == Project.id)
        .join(Series, Project.series_id == Series.id)
        # samo originali koji se prevode, ne objavljena srpska izdanja (referenca)
        .where(
            Page.kind == "original",
            TextBlock.kind == "sfx",
            Series.source_lang != Series.target_lang,
        )
    )
    counts = Counter()
    for text in session.scalars(query):
        source = flatten(text)
        if key(source) in glossary:
            continue
        counts.update(w for w in WORD.findall(source.upper()) if w not in glossary)
    return [
        {"source": word, "suggestion": lookup(word, glossary)[0] or adapt(word), "count": count}
        for word, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def apply_to_project(session: Session, project_id: int) -> int:
    """Ponovo prevede onomatopeje projekta po glosaru; ručno izmenjene i odobrene ne dira."""
    glossary = load(session)
    pages = session.scalars(
        select(Page).where(Page.project_id == project_id, Page.kind == "original")
    )
    changed = 0
    for page in pages:
        blocks = [
            block
            for block in page.blocks
            if block.kind == "sfx"
            and block.text.strip()
            and block.translation_status in ("none", "draft")
            and block.translation != translate(flatten(block.text), glossary)
        ]
        if not blocks:
            continue
        history.record(session, page, "onomatopeje po glosaru")
        for block in blocks:
            apply(block, glossary)
        changed += len(blocks)
    session.commit()
    return changed
