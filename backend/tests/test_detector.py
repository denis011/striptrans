import numpy as np

from app.services.detector import Detection, postprocess, text_blocks


def test_postprocess_scales_filters_and_clamps():
    labels = np.array([1, 2, 0, 1])
    boxes = np.array(
        [[64, 64, 128, 96], [0, 0, 32, 32], [60, 60, 140, 110], [600, 600, 700, 700]],
        dtype=np.float32,
    )
    scores = np.array([0.9, 0.55, 0.8, 0.7], dtype=np.float32)

    detections = postprocess(labels, boxes, scores, width=1280, height=1920)

    # slobodan tekst sa 0.55 je ispod praga; poslednji okvir izlazi van stranice i seče se
    assert [(d.label, d.box) for d in detections] == [
        ("text_bubble", (128.0, 192.0, 128.0, 96.0)),
        ("bubble", (120.0, 180.0, 160.0, 150.0)),
        ("text_bubble", (1200.0, 1800.0, 80.0, 120.0)),
    ]


def test_postprocess_keeps_best_of_overlapping_text_boxes():
    labels = np.array([1, 2])
    boxes = np.array([[100, 100, 200, 150], [105, 102, 205, 152]], dtype=np.float32)
    scores = np.array([0.9, 0.95], dtype=np.float32)

    detections = postprocess(labels, boxes, scores, width=640, height=640)

    assert [d.label for d in detections] == ["text_free"]


def test_text_blocks_get_kind_and_bubble():
    detections = [
        Detection("bubble", 0.9, (100, 100, 300, 200)),
        Detection("text_bubble", 0.9, (140, 130, 200, 120)),
        Detection("text_free", 0.8, (600, 50, 200, 60)),
        Detection("bubble", 0.8, (500, 500, 100, 100)),  # oblačić bez teksta, npr. „?"
    ]

    blocks = text_blocks(detections)

    assert [(b.kind, b.bubble) for b in blocks] == [
        ("speech", (100, 100, 300, 200)),
        ("caption", None),
    ]
