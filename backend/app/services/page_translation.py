"""Prevod blokova stranice: memorija prevoda, glosar, kontekst prethodne stranice, dužina."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GlossaryEntry, Page, TextBlock, TranslationMemory
from app.services import history
from app.services.glossary_suggest import flatten
from app.services.translation import Pairs, SourceBlock, is_too_long, shorten, translate_blocks

MEMORY_MODEL = "memorija"
CONTEXT_BLOCKS = 12
EXAMPLES = 8


class TranslationFailed(Exception):
    """Model nije vratio prevod."""


@dataclass
class PageTranslation:
    translated: int = 0
    from_memory: int = 0
    too_long: int = 0


def _blocks(session: Session, page_id: int) -> list[TextBlock]:
    query = select(TextBlock).where(TextBlock.page_id == page_id).order_by(TextBlock.position)
    return [block for block in session.scalars(query) if block.text.strip()]


def glossary_pairs(session: Session, series_id: int) -> Pairs:
    query = select(GlossaryEntry).where(
        GlossaryEntry.series_id == series_id, GlossaryEntry.status == "approved"
    )
    return [(entry.source, entry.target) for entry in session.scalars(query)]


def memory(session: Session, series_id: int) -> dict[str, str]:
    query = select(TranslationMemory).where(TranslationMemory.series_id == series_id)
    return {entry.source: entry.target for entry in session.scalars(query)}


def previous_page_context(session: Session, page: Page) -> Pairs:
    previous = session.scalar(
        select(Page).where(
            Page.project_id == page.project_id,
            Page.kind == page.kind,
            Page.position == page.position - 1,
        )
    )
    if previous is None:
        return []
    pairs = [
        (flatten(b.text), b.translation) for b in _blocks(session, previous.id) if b.translation
    ]
    return pairs[-CONTEXT_BLOCKS:]


def _apply(block: TextBlock, text: str, model: str, source: str) -> None:
    block.translation = text
    block.translation_model = model
    block.translation_status = "draft"
    block.translation_too_long = is_too_long(source, text)


def translate_page(
    session: Session, page: Page, model: str, include_drafts: bool = True
) -> PageTranslation:
    """Prevede blokove bez prevoda (i nacrte, ako treba); ručno izmenjene i odobrene ne dira."""
    statuses = {"none", "draft"} if include_drafts else {"none"}
    todo = [b for b in _blocks(session, page.id) if b.translation_status in statuses]
    result = PageTranslation()
    if not todo:
        return result
    history.record(session, page, "prevod stranice")
    series_id = page.project.series_id
    remembered = memory(session, series_id)
    remaining = []
    for block in todo:
        source = flatten(block.text)
        if source in remembered:
            _apply(block, remembered[source], MEMORY_MODEL, source)
            result.from_memory += 1
        else:
            remaining.append(block)
    if remaining:
        glossary = glossary_pairs(session, series_id)
        sources = [
            SourceBlock(n, b.kind, flatten(b.text, emphasis=True))
            for n, b in enumerate(remaining, start=1)
        ]
        examples = list(remembered.items())[:EXAMPLES]
        context = previous_page_context(session, page)
        translations = translate_blocks(model, sources, glossary, context, examples)
        for source, block in zip(sources, remaining, strict=True):
            text = translations.get(source.number)
            if not text:
                continue
            if is_too_long(source.text, text):
                shorter = shorten(model, source, text, glossary)
                if shorter and len(shorter) < len(text):
                    text = shorter
            _apply(block, text, model, source.text)
            result.translated += 1
    result.too_long = sum(block.translation_too_long for block in todo)
    session.commit()
    return result


def translate_block(
    session: Session, block: TextBlock, model: str, shorter: bool = False
) -> TextBlock:
    """Prevod jednog bloka (ili kraća verzija postojećeg prevoda); zamenjuje postojeći prevod."""
    page = block.page
    series_id = page.project.series_id
    source = SourceBlock(1, block.kind, flatten(block.text, emphasis=True))
    glossary = glossary_pairs(session, series_id)
    if shorter and block.translation:
        text = shorten(model, source, block.translation, glossary)
    else:
        examples = list(memory(session, series_id).items())[:EXAMPLES]
        context = previous_page_context(session, page)
        text = translate_blocks(model, [source], glossary, context, examples).get(1)
    if not text:
        raise TranslationFailed("model nije vratio prevod")
    _apply(block, text, model, source.text)
    session.commit()
    return block


def remember(session: Session, block: TextBlock) -> None:
    """Odobren prevod ulazi u memoriju prevoda serijala."""
    if not block.translation:
        return
    series_id = block.page.project.series_id
    source = flatten(block.text)
    entry = session.scalar(
        select(TranslationMemory).where(
            TranslationMemory.series_id == series_id, TranslationMemory.source == source
        )
    )
    if entry is None:
        session.add(TranslationMemory(series_id=series_id, source=source, target=block.translation))
    else:
        entry.target = block.translation
