import cv2
import numpy as np
import pytest

from app.services.inpaint import artwork_mask, inpaint, model_path, needs_inpaint, text_angle


def test_only_translated_signs_and_sounds_are_erased():
    assert needs_inpaint("sfx", "SWACK", "SCVAK")
    assert needs_inpaint("other", "SHERIFF", "ŠERIF")
    assert not needs_inpaint("other", "SHERIFF", "")  # bez prevoda natpis ostaje
    assert not needs_inpaint("sfx", "AH!", "AH!")  # isti tekst: nema šta da se menja
    # slobodan tekst (blok bez originala, dodat preko crteža): crtež ispod ostaje netaknut
    assert not needs_inpaint("other", "", "SLOBODAN TEKST")
    assert not needs_inpaint("title", "  ", "NASLOV")
    assert not needs_inpaint("speech", "CIAO", "ZDRAVO")  # oblačići se čiste belom bojom


def sound_effect(light_letters=False):
    background, ink = (0, 255) if light_letters else (255, 0)
    gray = np.full((300, 400), background, dtype=np.uint8)
    gray[100:200, 120:150] = ink  # debela slova onomatopeje
    gray[100:200, 200:230] = ink
    gray[100:200, 250:251] = ink  # tanka linija crteža (šrafura) unutar okvira
    gray[100:200, 10:60] = ink  # debeo crtež van okvira bloka
    return gray


def test_mask_covers_thick_letters_but_not_hatching_or_art_outside():
    for light in (False, True):
        gray = sound_effect(light_letters=light)
        probability = np.zeros(gray.shape, dtype=np.float32)

        mask = artwork_mask(gray, probability, (110, 90, 180, 120), "sfx")

        assert mask[150, 135] and mask[150, 215], light
        assert not mask[150, 30], light  # crtež sa strane ostaje
        assert not mask[150, 250], light  # tanka šrafura nije slovo


def test_angle_of_slanted_text():
    mask = np.zeros((400, 400), dtype=np.uint8)
    rect = cv2.boxPoints(((200, 200), (240, 60), -20)).astype(np.int32)
    cv2.fillPoly(mask, [rect], 1)

    assert text_angle(mask.astype(bool)) == pytest.approx(-20, abs=1.5)
    assert text_angle(np.zeros((10, 10), dtype=bool)) == 0.0


def test_missing_model_leaves_image_untouched(tmp_path):
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    mask = np.zeros((64, 64), dtype=bool)
    mask[10:20, 10:20] = True

    assert (inpaint(image, mask, str(tmp_path)) == image).all()


@pytest.mark.skipif(not model_path("/models").exists(), reason="LaMa model nije preuzet")
def test_lama_fills_masked_area_from_surroundings():
    image = np.full((128, 128, 3), 230, dtype=np.uint8)
    image[50:70, 40:90] = 0  # crna „slova" na svetloj pozadini
    mask = np.zeros((128, 128), dtype=bool)
    mask[45:75, 35:95] = True

    result = inpaint(image, mask, "/models")

    assert result[60, 60].mean() > 150  # slova su zamenjena pozadinom
    assert (result[~mask] == image[~mask]).all()  # van maske se ništa ne menja
