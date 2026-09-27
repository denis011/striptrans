"""Tekst prelomljen u više blokova (kolone uvodnika, oblačić u dva dela) prevodi se u jednom komadu.

Blok pokazuje na blok u kom se tekst nastavlja (`continues_id`); lanac ide modelu kao jedan tekst sa
oznakom ‖ na mestu preloma, a prevod se deli nazad po oznakama ili, ako ih model izgubi, srazmerno
dužini originala.
"""

import re

from app.models import TextBlock

MARK = "‖"
HYPHENATED = re.compile(r"(\w)-$")


def chains(blocks: list[TextBlock]) -> list[list[TextBlock]]:
    """Blokovi grupisani u lance po redosledu nastavka; blok bez veze je lanac od jednog bloka."""
    by_id = {block.id: block for block in blocks}
    continued = {block.continues_id for block in blocks if block.continues_id in by_id}
    groups, seen = [], set()
    heads = [block for block in blocks if block.id not in continued]
    # blokovi u krugu (A → B → A) nemaju početak: svaki postaje svoj lanac
    for head in heads + [block for block in blocks if block.id in continued]:
        group, block = [], head
        while block is not None and block.id not in seen:
            seen.add(block.id)
            group.append(block)
            block = by_id.get(block.continues_id)
        if group:
            groups.append(group)
    order = {block.id: index for index, block in enumerate(blocks)}
    return sorted(groups, key=lambda group: order[group[0].id])


def chain_of(block: TextBlock, blocks: list[TextBlock]) -> list[TextBlock]:
    return next(group for group in chains(blocks) if block in group)


def join(parts: list[str]) -> str:
    """Delovi sa oznakom preloma; reč rastavljena na kraju kolone (GIU- | DIZIO) ostaje cela."""
    parts = list(parts)
    for index in range(len(parts) - 1):
        first, _, rest = parts[index + 1].partition(" ")
        if HYPHENATED.search(parts[index]) and first[:1].isalpha():
            parts[index] = parts[index][:-1] + first
            parts[index + 1] = rest
    return f" {MARK} ".join(part.strip() for part in parts)


def split(translation: str, sources: list[str]) -> list[str]:
    """Prevod lanca po blokovima: po oznakama, inače srazmerno dužini originala, na granici reči."""
    if len(sources) == 1:
        return [translation.replace(MARK, " ").strip()]
    marked = [part.strip() for part in translation.split(MARK)]
    if len(marked) == len(sources) and all(marked):
        return marked
    words = translation.replace(MARK, " ").split()
    total = sum(len(source) for source in sources) or 1
    parts, start, used = [], 0, 0
    for source in sources[:-1]:
        used += len(source)
        end = max(round(len(words) * used / total), start)
        if end == start < len(words):  # deo bez ijedne reči samo kad reči nema dovoljno
            end += 1
        parts.append(" ".join(words[start:end]))
        start = end
    parts.append(" ".join(words[start:]))
    return parts
