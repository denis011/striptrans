"""Paneli stranice i redosled čitanja po panelima.

Ovakve stranice imaju pravougaone panele razdvojene belim razmacima, pa je dovoljan rekurzivni
XY-cut: stranica se seče po belim trakama, prvo vodoravno (redovi panela), pa uspravno.
"""

from collections.abc import Sequence

import numpy as np

from app.services.geometry import Box, intersection
from app.services.reading_order import reading_order

DARK_LEVEL = 160  # piksel tamniji od ovoga je mastilo
GUTTER_MAX_INK = 0.015  # red/kolona sa manje mastila pripada belom razmaku
MIN_GUTTER = 10  # piksela
MIN_PANEL_SHARE = 0.02  # deo površine stranice
MAX_DEPTH = 4


def _gutters(ink: np.ndarray) -> list[tuple[int, int]]:
    """Trake (početak, kraj) uzastopnih redova ili kolona bez mastila."""
    runs, start = [], None
    for index, empty in enumerate(ink <= GUTTER_MAX_INK):
        if empty and start is None:
            start = index
        elif not empty and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(ink)))
    return runs


def _segments(ink: np.ndarray) -> list[tuple[int, int]]:
    """Delovi između belih traka dovoljne širine; bele trake na ivicama se odsecaju."""
    length = len(ink)
    cuts = [(a, b) for a, b in _gutters(ink) if b - a >= MIN_GUTTER or a == 0 or b == length]
    segments, position = [], 0
    for start, end in cuts:
        if start > position:
            segments.append((position, start))
        position = end
    if position < length:
        segments.append((position, length))
    return segments


def _cut(dark: np.ndarray, x: int, y: int, depth: int, min_area: float) -> list[Box]:
    height, width = dark.shape
    if width * height < min_area:
        return []
    for axis in (1, 0):  # axis=1: udeo mastila po redovima → vodoravni rezovi
        segments = _segments(dark.mean(axis=axis))
        if len(segments) > 1 and depth < MAX_DEPTH:
            panels: list[Box] = []
            for start, end in segments:
                if axis == 1:
                    panels.extend(_cut(dark[start:end, :], x, y + start, depth + 1, min_area))
                else:
                    panels.extend(_cut(dark[:, start:end], x + start, y, depth + 1, min_area))
            return panels
    rows, cols = _segments(dark.mean(axis=1)), _segments(dark.mean(axis=0))
    if not rows or not cols:
        return []
    top, bottom, left, right = rows[0][0], rows[-1][1], cols[0][0], cols[-1][1]
    if (right - left) * (bottom - top) < min_area:
        return []
    return [(float(x + left), float(y + top), float(right - left), float(bottom - top))]


def detect_panels(gray: np.ndarray) -> list[Box]:
    """Paneli (x, y, širina, visina) u redosledu čitanja, iz sive slike stranice."""
    dark = (gray < DARK_LEVEL).astype(np.float32)
    min_area = MIN_PANEL_SHARE * gray.shape[0] * gray.shape[1]
    return _cut(dark, 0, 0, 0, min_area)


def _panel_for(block: Box, panels: Sequence[Box]) -> int:
    overlaps = [intersection(block, panel) for panel in panels]
    if max(overlaps) > 0:
        return overlaps.index(max(overlaps))
    cx, cy = block[0] + block[2] / 2, block[1] + block[3] / 2
    distances = [(p[0] + p[2] / 2 - cx) ** 2 + (p[1] + p[3] / 2 - cy) ** 2 for p in panels]
    return distances.index(min(distances))


def order_by_panels(blocks: Sequence[Box], panels: Sequence[Box]) -> list[int]:
    """Indeksi blokova: paneli redom, a unutar panela redovi odozgo nadole i sleva nadesno."""
    if not panels:
        return reading_order(blocks)
    groups: list[list[int]] = [[] for _ in panels]
    for index, block in enumerate(blocks):
        groups[_panel_for(block, panels)].append(index)
    order: list[int] = []
    for group in groups:
        local = reading_order([blocks[index] for index in group])
        order.extend(group[i] for i in local)
    return order
