from app.services.alignment import align_boxes

SOURCE = [(100, 100, 200, 80), (600, 100, 150, 60), (100, 900, 300, 100), (1200, 1500, 250, 120)]


def other_edition(boxes, scale=0.97, dx=15, dy=-10):
    return [(x * scale + dx, y * scale + dy, w * scale, h * scale) for x, y, w, h in boxes]


def test_aligns_scaled_and_shifted_scan():
    target = other_edition(SOURCE)

    assert align_boxes(SOURCE, (1800, 2450), target, (1746, 2376.5)) == {0: 0, 1: 1, 2: 2, 3: 3}


def test_merged_and_extra_bubbles_stay_unmatched():
    # srpsko izdanje nema treći oblačić, a ima jedan dodatni
    target = other_edition([SOURCE[1], SOURCE[0], SOURCE[3], (900, 2000, 200, 90)])

    assert align_boxes(SOURCE, (1800, 2450), target, (1746, 2376.5)) == {0: 1, 1: 0, 3: 2}


def test_small_bubble_with_extra_offset_is_matched_by_center_distance():
    source = [*SOURCE, (1000, 1800, 90, 50)]
    target = other_edition(SOURCE) + [(1000 * 0.97 + 15 + 45, 1800 * 0.97 - 10 + 30, 85, 48)]

    assert align_boxes(source, (1800, 2450), target, (1746, 2376.5))[4] == 4


def test_sfx_is_never_paired_with_speech():
    source = [(100, 100, 200, 80), (400, 400, 400, 200)]
    target = other_edition([(100, 100, 200, 80), (450, 450, 90, 50)])

    pairs = align_boxes(
        source, (1800, 2450), target, (1746, 2376.5), ["speech", "sfx"], ["speech", "speech"]
    )

    assert pairs == {0: 0}


def test_page_offset_finds_the_shift_between_two_editions():
    from app.services.alignment import page_offset

    def boxes(n):
        return [
            (100 + 37 * n % 300, 50 + 91 * n % 700, 180, 60),
            (400, 600 + 13 * n % 200, 150, 50),
        ]

    layouts = {n: (boxes(n), (800, 1200)) for n in range(1, 30)}
    # drugo izdanje ima dve strane više na početku i dvostruko veći sken
    shifted = {
        n + 2: ([(x * 2, y * 2, w * 2, h * 2) for x, y, w, h in boxes], (1600, 2400))
        for n, (boxes, _) in layouts.items()
    }
    assert page_offset(layouts, shifted) == 2
    assert page_offset(layouts, layouts) == 0
