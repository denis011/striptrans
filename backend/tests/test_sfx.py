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
