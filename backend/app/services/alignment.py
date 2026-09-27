"""Uparivanje blokova dva izdanja iste stranice (npr. italijansko ↔ srpsko)."""

from collections.abc import Sequence
from math import hypot
from statistics import median

from app.services.geometry import Box, match_boxes, overlap

MIN_OVERLAP = 0.3
# mali oblačići se često ne preklapaju dovoljno, pa važi i blizina centara (u delovima dijagonale)
MAX_CENTER_DISTANCE = 1.0


def _center(box: Box) -> tuple[float, float]:
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def _diagonal(box: Box) -> float:
    return hypot(box[2], box[3])


def align_boxes(
    source: list[Box],
    source_size: tuple[float, float],
    target: list[Box],
    target_size: tuple[float, float],
    source_kinds: Sequence[str] | None = None,
    target_kinds: Sequence[str] | None = None,
) -> dict[int, int]:
    """Parovi (indeks izvornog okvira → indeks okvira drugog izdanja).

    Okviri drugog izdanja se skaliraju na veličinu izvorne stranice, iz prvih parova se procenjuje
    pomak skena, a zatim se uparuje po preklapanju ili blizini centara. Onomatopeja se ne uparuje
    sa ostalim vrstama blokova.
    """
    scale_x, scale_y = source_size[0] / target_size[0], source_size[1] / target_size[1]
    scaled = [(x * scale_x, y * scale_y, w * scale_x, h * scale_y) for x, y, w, h in target]
    first = match_boxes(scaled, source, MIN_OVERLAP)
    if first:
        dx = median(_center(source[j])[0] - _center(scaled[i])[0] for i, j in first.items())
        dy = median(_center(source[j])[1] - _center(scaled[i])[1] for i, j in first.items())
        scaled = [(x + dx, y + dy, w, h) for x, y, w, h in scaled]

    candidates = []
    for i, box in enumerate(source):
        for j, other in enumerate(scaled):
            if (
                source_kinds
                and target_kinds
                and (source_kinds[i] == "sfx") != (target_kinds[j] == "sfx")
            ):
                continue
            (sx, sy), (tx, ty) = _center(box), _center(other)
            distance = hypot(sx - tx, sy - ty) / max(_diagonal(box), _diagonal(other))
            if overlap(box, other) >= MIN_OVERLAP or distance <= MAX_CENTER_DISTANCE:
                candidates.append((distance, i, j))
    pairs: dict[int, int] = {}
    used: set[int] = set()
    for _, i, j in sorted(candidates):
        if i not in pairs and j not in used:
            pairs[i] = j
            used.add(j)
    return pairs


Layout = tuple[list[Box], tuple[float, float]]  # okviri blokova stranice i njena veličina
MAX_PAGE_OFFSET = 8


def _layout_score(source: Layout, target: Layout) -> float:
    """Koliko se rasporedi blokova dve stranice poklapaju (0–1), bez procene pomaka skena."""
    (boxes, size), (other, other_size) = source, target
    if not boxes or not other:
        return 0.0
    scale_x, scale_y = size[0] / other_size[0], size[1] / other_size[1]
    scaled = [(x * scale_x, y * scale_y, w * scale_x, h * scale_y) for x, y, w, h in other]
    return len(match_boxes(scaled, boxes, MIN_OVERLAP)) / max(len(boxes), len(other))


def page_offset(
    source: dict[int, Layout], target: dict[int, Layout], limit: int = MAX_PAGE_OFFSET
) -> int:
    """Pomak strana drugog izdanja (strana p ↔ p + pomak) pri kome se rasporedi blokova najbolje
    poklapaju: skenovi se razlikuju po korici, impresumu i reklamama, pa isti redni broj nije ista
    strana priče."""

    def score(offset: int) -> float:
        return sum(
            _layout_score(layout, target[position + offset])
            for position, layout in source.items()
            if position + offset in target
        )

    return max(range(-limit, limit + 1), key=lambda offset: (score(offset), -abs(offset)))
