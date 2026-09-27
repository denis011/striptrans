"""Lektura stranice: upozorenja po bloku (pravopis, glosar, dužina)."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DictionaryWord, Page, TextBlock
from app.services.glossary_suggest import flatten
from app.services.page_translation import glossary_pairs
from app.services.spellcheck import allowed_words, non_serbian_words, unknown_words
from app.services.translation import Pairs, emphasis_count, is_too_long, relevant_glossary

SKIP_KINDS = {"sfx"}  # onomatopeje nisu reči iz rečnika


def uses_glossary_term(translation: str, target: str) -> bool:
    """Srpski oblik iz glosara u prevodu, uz padežne nastavke (RAMON → RAMONE, NORA → NORU)."""
    text = translation.upper()
    return all(word[: max(3, len(word) - 2)] in text for word in target.upper().split())


@dataclass
class BlockReview:
    block_id: int
    position: int
    unknown: list[str] = field(default_factory=list)
    glossary_missing: list[str] = field(default_factory=list)
    non_serbian: list[str] = field(default_factory=list)  # hrvatske i ijekavske reči
    too_long: bool = False
    emphasis_missing: bool = False  # original ima naglašene reči (`*…*`), prevod ne u istom broju

    @property
    def clean(self) -> bool:
        return not (
            self.unknown
            or self.glossary_missing
            or self.non_serbian
            or self.too_long
            or self.emphasis_missing
        )


def dictionary_words(session: Session, series_id: int) -> list[str]:
    query = select(DictionaryWord.word).where(DictionaryWord.series_id == series_id)
    return list(session.scalars(query))


def review_block(block: TextBlock, glossary: Pairs, allowed: frozenset[str]) -> BlockReview:
    result = BlockReview(block_id=block.id, position=block.position)
    translation = (block.translation or "").strip()
    if not translation:
        return result
    source = flatten(block.text)
    result.too_long = is_too_long(source, translation)
    marked = emphasis_count(flatten(block.text, emphasis=True))
    result.emphasis_missing = bool(marked) and emphasis_count(translation) != marked
    result.glossary_missing = [
        target
        for _, target in relevant_glossary(glossary, source)
        if not uses_glossary_term(translation, target)
    ]
    if block.kind not in SKIP_KINDS:
        result.non_serbian = non_serbian_words(translation)
        unknown = unknown_words(translation, allowed)
        result.unknown = [word for word in unknown if word.upper() not in result.non_serbian]
    return result


def review_page(session: Session, page: Page) -> list[BlockReview]:
    series_id = page.project.series_id
    glossary = glossary_pairs(session, series_id)
    allowed = allowed_words(
        *(target for _, target in glossary), *dictionary_words(session, series_id)
    )
    blocks = session.scalars(
        select(TextBlock).where(TextBlock.page_id == page.id).order_by(TextBlock.position)
    )
    return [review_block(block, glossary, allowed) for block in blocks]
