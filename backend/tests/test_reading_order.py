from app.services.reading_order import reading_order


def test_side_by_side_blocks_read_left_to_right():
    assert reading_order([(300, 10, 100, 50), (10, 10, 100, 50)]) == [1, 0]


def test_slightly_staggered_blocks_stay_in_one_row():
    # desni oblačić je malo viši, ali se čita posle levog
    assert reading_order([(10, 30, 100, 60), (300, 10, 100, 60)]) == [0, 1]


def test_rows_go_top_to_bottom_before_left_to_right():
    boxes = [(10, 400, 100, 50), (300, 10, 100, 50), (10, 20, 100, 50)]
    assert reading_order(boxes) == [2, 1, 0]


def test_grid_of_blocks():
    boxes = [
        (400, 300, 80, 40),
        (10, 10, 80, 40),
        (10, 300, 80, 40),
        (400, 10, 80, 40),
    ]
    assert reading_order(boxes) == [1, 3, 2, 0]


def test_empty_page():
    assert reading_order([]) == []


def test_left_bubble_slightly_lower_is_read_first():
    # Ramon 12, str. 10: „RAMON!..." levo i niže, „NORAH!" desno i više
    assert reading_order([(440, 1660, 170, 45), (100, 1690, 170, 50)]) == [1, 0]
