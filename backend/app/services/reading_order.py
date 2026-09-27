"""Redosled čitanja tekst blokova za strip koji se čita sleva nadesno."""

from collections.abc import Sequence

from app.services.geometry import Box

# 0,1 je izabrano benchmarkom Faze 2: oblačić levo i malo niže čita se pre desnog
ROW_OVERLAP = 0.1


def reading_order(boxes: Sequence[Box], row_overlap: float = ROW_OVERLAP) -> list[int]:
    """Indeksi okvira u redosledu čitanja.

    Okvir pripada redu ako se vertikalno preklapa sa njim bar `row_overlap` visine nižeg od
    njih dvoje. Redovi idu odozgo nadole, a okviri u redu sleva nadesno. Paneli se uzimaju u
    obzir tek u podfazi 2c.
    """
    rows: list[list[int]] = []
    bounds: list[tuple[float, float]] = []
    for index in sorted(range(len(boxes)), key=lambda i: boxes[i][1]):
        _, top, _, height = boxes[index]
        bottom = top + height
        for row, (row_top, row_bottom) in enumerate(bounds):
            overlap = min(bottom, row_bottom) - max(top, row_top)
            if overlap >= row_overlap * min(height, row_bottom - row_top):
                rows[row].append(index)
                bounds[row] = (min(top, row_top), max(bottom, row_bottom))
                break
        else:
            rows.append([index])
            bounds.append((top, bottom))
    return [index for row in rows for index in sorted(row, key=lambda i: boxes[i][0])]
