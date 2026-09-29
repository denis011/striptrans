"""Prevod blokova stranice: memorija prevoda, glosar, kontekst prethodne stranice, dužina."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GlossaryEntry, Page, TextBlock, TranslationMemory
from app.services import chains, history, sfx_glossary, styles
from app.services.glossary_suggest import flatten
from app.services.translation import (
    Pairs,
    SourceBlock,
    Style,
    is_too_long,
    shorten,
    translate_blocks,
)

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


def _apply(block: TextBlock, text: str, model: str, source: str, note: str | None = None) -> None:
    block.translation = text
    block.translation_model = model
    block.translation_status = "draft"
    block.translation_too_long = is_too_long(source, text)
    block.translation_note = note or None


def _chain_source(number: int, group: list[TextBlock]) -> SourceBlock:
    """Lanac blokova kao jedan tekst za model, sa oznakom preloma između blokova."""
    return SourceBlock(
        number, group[0].kind, chains.join([flatten(b.text, emphasis=True) for b in group])
    )


def _apply_chain(
    group: list[TextBlock],
    text: str,
    model: str,
    statuses: set[str],
    force: TextBlock | None = None,
    note: str | None = None,
) -> int:
    """Prevod lanca podeljen po blokovima; ručno izmenjeni i odobreni delovi ostaju.

    Napomena prevodioca za ceo lanac ide uz prvi blok.
    """
    sources = [flatten(block.text, emphasis=True) for block in group]
    applied = 0
    for block, part, source in zip(group, chains.split(text, sources), sources, strict=True):
        # prazan blok se uvek popunjava (i kad je ostao „izmenjen" posle brisanja prevoda)
        eligible = block.translation_status in statuses or not block.translation.strip()
        if part and (eligible or block is force):
            _apply(block, part, model, source, note if block is group[0] else None)
            applied += 1
    return applied


def translate_page(
    session: Session, page: Page, model: str, include_drafts: bool = True
) -> PageTranslation:
    """Prevede blokove bez prevoda (i nacrte, ako treba); ručno izmenjene i odobrene ne dira.

    Blokovi povezani u lanac (tekst prelomljen u kolone) idu modelu kao jedan tekst.
    """
    statuses = {"none", "draft"} if include_drafts else {"none"}
    groups = [
        group
        for group in chains.chains(_blocks(session, page.id))
        if any(block.translation_status in statuses for block in group)
    ]
    result = PageTranslation()
    if not groups:
        return result
    history.record(session, page, "prevod stranice")
    series_id = page.project.series_id
    remembered = memory(session, series_id)
    sounds = sfx_glossary.load(session)
    style = styles.for_series(session, page.project.series)
    remaining: list[list[TextBlock]] = []
    for group in groups:
        block = group[0]
        source = flatten(block.text)
        if len(group) > 1:
            remaining.append(group)
        elif block.kind == "sfx":  # onomatopeje: glosar i pravilo, bez modela
            sfx_glossary.apply(block, sounds)
            result.translated += 1
        elif source in remembered:
            _apply(block, remembered[source], MEMORY_MODEL, source)
            result.from_memory += 1
        else:
            remaining.append(group)
    if remaining:
        glossary = glossary_pairs(session, series_id)
        sources = [_chain_source(n, group) for n, group in enumerate(remaining, start=1)]
        examples = list(remembered.items())[:EXAMPLES]
        context = previous_page_context(session, page)
        notes: dict[int, str] = {}
        translations = translate_blocks(model, sources, glossary, context, examples, style, notes)
        for source, group in zip(sources, remaining, strict=True):
            text = translations.get(source.number)
            if not text:
                continue
            note = notes.get(source.number)
            if len(group) > 1:
                result.translated += _apply_chain(group, text, model, statuses, note=note)
                continue
            if is_too_long(source.text, text):
                shorter = shorten(model, source, text, glossary, style)
                if shorter and len(shorter) < len(text):
                    text = shorter
            _apply(group[0], text, model, source.text, note)
            result.translated += 1
    result.too_long = sum(block.translation_too_long for group in groups for block in group)
    session.commit()
    return result


def _block_translation(
    session: Session,
    block: TextBlock,
    group: list[TextBlock],
    model: str,
    shorter: bool,
    style: Style,
) -> tuple[str, str | None]:
    """Prevod bloka (ili celog lanca, ako je blok deo lanca) i napomena prevodioca."""
    page = block.page
    series_id = page.project.series_id
    glossary = glossary_pairs(session, series_id)
    if len(group) > 1 and not shorter:
        source = _chain_source(1, group)
    else:
        source = SourceBlock(1, block.kind, flatten(block.text, emphasis=True))
    notes: dict[int, str] = {}
    if shorter and block.translation:
        text = shorten(model, source, block.translation, glossary, style)
        return text or "", block.translation_note
    examples = list(memory(session, series_id).items())[:EXAMPLES]
    context = previous_page_context(session, page)
    text = translate_blocks(model, [source], glossary, context, examples, style, notes).get(1)
    return text or "", notes.get(1)


def translate_block(
    session: Session, block: TextBlock, model: str, shorter: bool = False
) -> TextBlock:
    """Prevod jednog bloka (ili kraća verzija postojećeg prevoda); zamenjuje postojeći prevod."""
    page = block.page
    group = chains.chain_of(block, _blocks(session, page.id)) if block.text.strip() else [block]
    if block.kind == "sfx" and len(group) == 1:
        sfx_glossary.apply(block, sfx_glossary.load(session))
        session.commit()
        return block
    style = styles.for_series(session, page.project.series)
    text, note = _block_translation(session, block, group, model, shorter, style)
    if not text:
        raise TranslationFailed("model nije vratio prevod")
    if len(group) > 1 and not shorter:
        # deo lanca: prevodi se ceo tekst, a menjaju se ovaj blok i delovi bez ručnih izmena
        _apply_chain(group, text, model, {"none", "draft"}, force=block, note=note)
    else:
        _apply(block, text, model, flatten(block.text, emphasis=True), note)
    session.commit()
    return block


def preview_block(
    session: Session, block: TextBlock, model: str, style_id: int | None = None
) -> tuple[str, str | None]:
    """Probni prevod sa izabranim stilom; ništa se ne upisuje. Za deo lanca vraća njegov deo."""
    group = chains.chain_of(block, _blocks(session, block.page.id))
    style = styles.for_series(session, block.page.project.series, style_id)
    text, note = _block_translation(session, block, group, model, False, style)
    if not text:
        raise TranslationFailed("model nije vratio prevod")
    if len(group) > 1:
        sources = [flatten(b.text, emphasis=True) for b in group]
        text = chains.split(text, sources)[group.index(block)]
    return text, note


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
