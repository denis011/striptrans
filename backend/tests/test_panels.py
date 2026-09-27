import numpy as np
import pytest

from app.services.panels import detect_panels, order_by_panels


def page_with_panels(panels, width=1000, height=1400, bubble=None):
    """Bela stranica sa panelima: crni okvir i gusto išrafiran sadržaj."""
    page = np.full((height, width), 255, dtype=np.uint8)
    for x, y, w, h in panels:
        page[y : y + h, x : x + w] = 255
        page[y : y + h : 6, x : x + w] = 0  # šrafura
        page[y : y + 4, x : x + w] = page[y + h - 4 : y + h, x : x + w] = 0
        page[y : y + h, x : x + 4] = page[y : y + h, x + w - 4 : x + w] = 0
    if bubble:  # beli oblačić sa okvirom i tekstom koji prelazi preko razmaka
        x, y, w, h = bubble
        page[y : y + h, x : x + w] = 255
        page[y : y + 3, x : x + w] = page[y + h - 3 : y + h, x : x + w] = 0
        page[y : y + h, x : x + 3] = page[y : y + h, x + w - 3 : x + w] = 0
        page[y + 10 : y + h - 10 : 12, x + 20 : x + w // 3] = 0
    return page


LAYOUT = [
    (40, 40, 920, 400),  # prvi red: jedan panel
    (40, 470, 440, 420),  # drugi red: dva panela
    (510, 470, 450, 420),
    (40, 920, 600, 440),  # treći red: dva nejednaka
    (670, 920, 290, 440),
]


def assert_boxes(found, expected, tolerance=8):
    assert len(found) == len(expected), found
    for box, target in zip(found, expected, strict=True):
        assert box == pytest.approx(target, abs=tolerance)


def test_detects_panels_in_reading_order():
    assert_boxes(detect_panels(page_with_panels(LAYOUT)), LAYOUT)


def test_bubble_over_gutter_does_not_merge_rows():
    page = page_with_panels(LAYOUT, bubble=(300, 400, 300, 100))
    assert_boxes(detect_panels(page), LAYOUT)


def test_tall_panel_next_to_stacked_panels():
    layout = [(40, 40, 450, 1320), (520, 40, 440, 640), (520, 720, 440, 640)]
    assert_boxes(detect_panels(page_with_panels(layout)), layout)


def test_blank_page_has_no_panels():
    assert detect_panels(np.full((1400, 1000), 255, dtype=np.uint8)) == []


def test_blocks_are_read_panel_by_panel():
    panels = [(0, 0, 500, 1000), (500, 0, 500, 500), (500, 500, 500, 500)]
    blocks = [
        (600, 100, 100, 50),  # desno gore, vrlo visoko
        (100, 800, 100, 50),  # levi visoki panel, nisko
        (600, 700, 100, 50),  # desno dole
        (100, 100, 100, 50),  # levi panel, gore
    ]
    assert order_by_panels(blocks, panels) == [3, 1, 0, 2]


def test_block_outside_panels_goes_to_nearest_panel():
    panels = [(0, 0, 500, 500), (0, 600, 500, 500)]
    blocks = [(100, 1150, 100, 30), (100, 100, 100, 30)]
    assert order_by_panels(blocks, panels) == [1, 0]


def test_without_panels_uses_rows():
    assert order_by_panels([(300, 10, 50, 50), (10, 10, 50, 50)], []) == [1, 0]
