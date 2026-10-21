import numpy as np
from PIL import Image

from app.services.sfx import mask_candidates, sfx_candidates


def test_mask_candidates_keep_only_large_new_regions():
    mask = np.zeros((1000, 800), dtype=np.float32)
    mask[100:220, 100:400] = 0.9  # onomatopeja
    mask[500:540, 100:160] = 0.9  # tekst oblačića koji je detektor već našao
    mask[800:810, 700:710] = 0.9  # mrlja na crtežu

    [(x, y, w, h)] = mask_candidates(mask, known=[(90, 490, 100, 70)])

    assert x <= 100 and y <= 100 and x + w >= 400 and y + h >= 220


def test_missing_model_gives_no_candidates(tmp_path):
    image = Image.new("L", (100, 100), 255)
    assert sfx_candidates(image, [], tmp_path / "nema.onnx") == []


def test_letters_of_one_big_sound_are_one_candidate():
    mask = np.zeros((1000, 800), dtype=np.float32)
    for x in (100, 260, 420):  # S W A: krupna slova, razmak 60 px (više od dilatacije)
        mask[100:200, x : x + 100] = 0.9
    mask[600:700, 100:200] = 0.9  # drugi zvuk, daleko

    candidates = mask_candidates(mask, known=[])

    assert len(candidates) == 2
    x, y, w, h = min(candidates, key=lambda box: box[1])
    assert x <= 100 and x + w >= 520


def test_two_sounds_one_above_the_other_stay_apart():
    mask = np.zeros((1000, 800), dtype=np.float32)
    mask[100:250, 100:500] = 0.9  # THUD
    mask[300:450, 250:650] = 0.9  # TUMP, ispod i malo desno (drugi panel)

    assert len(mask_candidates(mask, known=[])) == 2
