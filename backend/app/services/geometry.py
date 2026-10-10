"""Pravougaonici u pikselima stranice: (x, y, širina, visina)."""

Box = tuple[float, float, float, float]
GRAY_MODES = ("L", "1", "LA")  # crno-bela strana: čisti se, krpi i izvozi siva


def runs(values) -> list[tuple[int, int]]:
    """Neprekinuti delovi (početak, kraj) gde je vrednost tačna, npr. projekcija mastila."""
    found, start = [], None
    for index, value in enumerate(values):
        if value and start is None:
            start = index
        elif not value and start is not None:
            found.append((start, index))
            start = None
    if start is not None:
        found.append((start, len(values)))
    return found


def area(box: Box) -> float:
    return max(0.0, box[2]) * max(0.0, box[3])


def intersection(a: Box, b: Box) -> float:
    width = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    height = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, width) * max(0.0, height)


def iou(a: Box, b: Box) -> float:
    shared = intersection(a, b)
    union = area(a) + area(b) - shared
    return shared / union if union > 0 else 0.0


def rect_polygon(box: Box) -> list[list[float]]:
    x, y, width, height = box
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


def overlap(a: Box, b: Box) -> float:
    """Preklapanje u odnosu na manji okvir (manje zavisi od toga koliko je okvir tesan)."""
    smaller = min(area(a), area(b))
    return intersection(a, b) / smaller if smaller > 0 else 0.0


def match_boxes(predicted: list[Box], gold: list[Box], threshold: float = 0.5) -> dict[int, int]:
    """Pohlepno uparivanje, najveće preklapanje prvo: indeks predviđenog → indeks zlatnog okvira."""
    candidates = sorted(
        ((overlap(p, g), i, j) for i, p in enumerate(predicted) for j, g in enumerate(gold)),
        reverse=True,
    )
    matches: dict[int, int] = {}
    used: set[int] = set()
    for score, i, j in candidates:
        if score < threshold:
            break
        if i not in matches and j not in used:
            matches[i] = j
            used.add(j)
    return matches
