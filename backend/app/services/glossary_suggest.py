"""Predlozi za glosar iz uparenih blokova originala i objavljenog prevoda."""

import json
import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GLOSSARY_KINDS, GlossaryEntry, Page, TextBlock
from app.services import llm
from app.services.alignment import Layout, align_boxes, page_offset

if TYPE_CHECKING:
    from app.jobs import JobContext

PROMPT = """You compare an Italian comic book page with its published Serbian translation.
Below are aligned balloon pairs (IT = Italian original, SR = Serbian edition).
Extract glossary entries where the Serbian edition uses a specific translation or
transliteration: character names, place names, recurring exclamations, curses or idioms,
and sound effects. Only use items that actually occur in the pairs. Give names in their
base (nominative) form, in uppercase as in the lettering, Serbian in Latin script.
Skip items that are identical in both languages. If there are no pairs, return no entries.

"""

SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "kind": {"type": "string", "enum": list(GLOSSARY_KINDS)},
                },
                "required": ["source", "target", "kind"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entries"],
    "additionalProperties": False,  # OpenAI u strogom režimu traži ovo na svakom objektu
}


def clean_term(value: str) -> str:
    """Glosar se poredi sa tekstom letteringa: velika slova, jednostruki razmaci."""
    return " ".join(value.upper().split())


EMPHASIS_BREAK = re.compile(r"-\*[ \t]*\n\s*\*")  # naglašena rastavljena reč: *ANCO-*\n*RA*


def flatten(text: str, emphasis: bool = False) -> str:
    """Tekst bloka u jednom redu, sa spojenim rastavljenim rečima.

    Oznake naglaska (`*reč*`) ostaju samo uz `emphasis` (prevod); glosar, memorija i lektura
    porede tekst bez njih.
    """
    text = EMPHASIS_BREAK.sub("", text)
    if not emphasis:
        text = text.replace("*", "")
    return clean_term(re.sub(r"-[ \t]*\n\s*", "", text))


def _blocks(session: Session, page: Page) -> list[TextBlock]:
    query = select(TextBlock).where(TextBlock.page_id == page.id).order_by(TextBlock.position)
    return [block for block in session.scalars(query) if block.text.strip()]


def layouts(session: Session, pages: dict[int, Page]) -> dict[int, Layout]:
    """Rasporedi blokova po stranama, za procenu pomaka strana između dva izdanja."""
    return {
        position: (
            [(b.x, b.y, b.width, b.height) for b in _blocks(session, page)],
            (page.width, page.height),
        )
        for position, page in pages.items()
    }


def paired_positions(
    session: Session, source_pages: dict[int, Page], reference_pages: dict[int, Page]
) -> list[tuple[int, int]]:
    """Parovi rednih brojeva strana (original, drugo izdanje), uz pomak strana između skenova."""
    offset = page_offset(layouts(session, source_pages), layouts(session, reference_pages))
    return [
        (position, position + offset)
        for position in sorted(source_pages)
        if position + offset in reference_pages
    ]


def page_pairs(session: Session, original: Page, reference: Page) -> list[tuple[str, str]]:
    source, target = _blocks(session, original), _blocks(session, reference)
    matches = align_boxes(
        [(b.x, b.y, b.width, b.height) for b in source],
        (original.width, original.height),
        [(b.x, b.y, b.width, b.height) for b in target],
        (reference.width, reference.height),
        [b.kind for b in source],
        [b.kind for b in target],
    )
    return [(flatten(source[i].text), flatten(target[j].text)) for i, j in sorted(matches.items())]


def extract_entries(model: str, pairs: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    lines = "\n".join(f"{n}. IT: {it} | SR: {sr}" for n, (it, sr) in enumerate(pairs, start=1))
    result = llm.translation_client(model).generate(
        PROMPT + lines, model, max_tokens=1500, temperature=0, format=SCHEMA
    )
    try:
        items = json.loads(result.response).get("entries", [])
    except (ValueError, AttributeError):
        return []
    italian = " ".join(it for it, _ in pairs)
    entries = []
    for item in items:
        source, target = (
            clean_term(str(item.get("source", ""))),
            clean_term(str(item.get("target", ""))),
        )
        kind = item.get("kind")
        # model ponekad izmisli izraz ili vrati isti tekst: zadržavaju se samo stvarni prevodi
        if source and target and source != target and kind in GLOSSARY_KINDS and source in italian:
            entries.append((source, target, kind))
    return entries


def store_suggestions(
    session: Session, series_id: int, counts: Counter, kinds: dict[tuple[str, str], Counter]
) -> int:
    query = select(GlossaryEntry).where(GlossaryEntry.series_id == series_id)
    existing = {(entry.source, entry.target): entry for entry in session.scalars(query)}
    added = 0
    for (source, target), count in counts.items():
        entry = existing.get((source, target))
        if entry is None:
            session.add(
                GlossaryEntry(
                    series_id=series_id,
                    source=source,
                    target=target,
                    kind=kinds[(source, target)].most_common(1)[0][0],
                    status="suggested",
                    origin="reference",
                    occurrences=count,
                )
            )
            added += 1
        elif entry.status == "suggested":
            entry.occurrences += count
    session.commit()
    return added


def suggest_from_projects(ctx: "JobContext") -> dict:
    payload, session = ctx.job.payload, ctx.session

    def originals(project_id: int) -> dict[int, Page]:
        query = select(Page).where(Page.project_id == project_id, Page.kind == "original")
        return {page.position: page for page in session.scalars(query)}

    source_pages, reference_pages = (
        originals(payload["project_id"]),
        originals(payload["reference_project_id"]),
    )
    positions = paired_positions(session, source_pages, reference_pages)
    counts: Counter = Counter()
    kinds: dict[tuple[str, str], Counter] = defaultdict(Counter)
    ctx.report(0, len(positions))
    for index, (position, other) in enumerate(positions, start=1):
        ctx.check_cancelled()
        pairs = page_pairs(session, source_pages[position], reference_pages[other])
        if pairs:
            for source, target, kind in set(extract_entries(payload["model"], pairs)):
                counts[(source, target)] += 1
                kinds[(source, target)][kind] += 1
        ctx.report(index)
    added = store_suggestions(session, payload["series_id"], counts, kinds)
    return {"pages": len(positions), "found": len(counts), "added": added}
