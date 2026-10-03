import io

import numpy as np
from factories import create_page
from PIL import Image

from app.services import cleaning
from app.services.cleaning import Stroke, apply_strokes, bubble_shape, clean_image, dark_background
from worker.main import run_once


def bubble_page(background=255):
    """Oblačić sa crnom ivicom i „tekstom" (crni pravougaonik) u sredini; maska pokriva tekst."""
    image = np.full((200, 300, 3), background, dtype=np.uint8)
    image[40:42, 40:260] = 0  # ivica oblačića, izvan okvira teksta
    image[90:110, 100:200] = 0  # tekst
    probability = np.zeros((200, 300), dtype=np.float32)
    probability[90:110, 100:200] = 0.9
    return image, probability


def test_text_in_bubble_is_covered_with_bubble_background():
    image, probability = bubble_page()

    cleaned, covered, result = clean_image(image, [("speech", (95, 85, 110, 30))], probability)

    assert (cleaned[90:110, 100:200] == 255).all()
    assert (cleaned[40:42, 40:260] == 0).all()  # ivica oblačića ostaje
    assert covered[100, 150] and not covered[41, 150]
    assert (result.blocks, result.pixels) == (1, int(covered.sum()))
    assert (image[90:110, 100:200] == 0).all()  # original se ne menja


def test_fill_uses_bubble_color_not_pure_white():
    image, probability = bubble_page(background=230)

    cleaned, _, _ = clean_image(image, [("caption", (95, 85, 110, 30))], probability)

    assert (cleaned[90:110, 100:200] == 230).all()


def test_faint_letter_edges_left_by_the_detector_are_wiped():
    image, probability = bubble_page()
    image[84:87, 100:200] = 245  # meka ivica slova koju maska ne pokriva

    cleaned, covered, _ = clean_image(image, [("speech", (95, 85, 110, 30))], probability)

    assert (cleaned[84:87, 100:200] == 255).all()
    assert covered[85, 150]


def test_faint_pixels_behind_ink_are_not_touched():
    image, probability = bubble_page()
    image[116:119, :] = 0  # crta preko celog okvira: ispod nje je crtež, ne oblačić
    image[119:121, 120:180] = 245

    cleaned, covered, _ = clean_image(image, [("speech", (95, 85, 110, 30))], probability)

    assert (cleaned[119:121, 120:180] == 245).all()
    assert not covered[120, 150]


def test_signs_and_sound_effects_over_artwork_are_left_alone():
    image, probability = bubble_page()

    for kind in ("sfx", "other"):
        cleaned, covered, result = clean_image(image, [(kind, (95, 85, 110, 30))], probability)
        assert (cleaned == image).all() and not covered.any() and result.blocks == 0


def test_mask_outside_the_block_is_ignored():
    image, probability = bubble_page()
    probability[150:160, 20:60] = 0.9  # tekst negde drugde na stranici (npr. crtež)

    cleaned, covered, _ = clean_image(image, [("speech", (95, 85, 110, 30))], probability)

    assert not covered[150:160, 20:60].any()


def test_clean_page_job_saves_image_and_mask(client, monkeypatch):
    monkeypatch.setattr(cleaning, "text_mask", lambda image, path: fake_mask(image))
    monkeypatch.setattr(cleaning, "ink_letters", lambda image, blocks: fake_letters(image))
    page = create_page(client)
    block = {"x": 100, "y": 100, "width": 200, "height": 80, "text": "CIAO", "kind": "speech"}
    client.post(f"/api/pages/{page['id']}/blocks", json=block)
    assert client.get(f"/api/pages/{page['id']}/clean-image").status_code == 404

    job = client.post(f"/api/pages/{page['id']}/clean").json()
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)

    finished = client.get(f"/api/jobs/{job['id']}").json()
    assert finished["status"] == "done" and finished["result"]["blocks"] == 1
    image = client.get(f"/api/pages/{page['id']}/clean-image")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    project_id = client.get("/api/projects").json()[0]["id"]
    assert client.get(f"/api/projects/{project_id}/pages").json()[0]["cleaned_at"] is not None


def test_block_that_ocr_never_read_is_not_erased(client, monkeypatch):
    """Obrada prekinuta posle detekcije: oblačić nema prevod, pa original ostaje na strani."""
    from app.models import TextBlock

    monkeypatch.setattr(cleaning, "text_mask", lambda image, path: fake_mask(image))
    monkeypatch.setattr(cleaning, "ink_letters", lambda image, blocks: fake_letters(image))
    page = create_page(client)
    block = {"x": 100, "y": 100, "width": 200, "height": 80, "kind": "speech"}
    created = client.post(f"/api/pages/{page['id']}/blocks", json=block).json()
    state = client.app.state
    with state.session_factory() as session:
        # detektor ga je našao, OCR nije stigao
        session.get(TextBlock, created["id"]).source = "auto"
        session.commit()

    job = client.post(f"/api/pages/{page['id']}/clean").json()
    run_once(state.session_factory, "w1", state.settings)

    result = client.get(f"/api/jobs/{job['id']}").json()["result"]
    assert (result["blocks"], result["pixels"]) == (0, 0)


def test_clean_project_skips_pages_without_blocks(client, monkeypatch):
    monkeypatch.setattr(cleaning, "text_mask", lambda image, path: fake_mask(image))
    monkeypatch.setattr(cleaning, "ink_letters", lambda image, blocks: fake_letters(image))
    create_page(client)
    project_id = client.get("/api/projects").json()[0]["id"]

    job = client.post(f"/api/projects/{project_id}/clean").json()
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)

    assert client.get(f"/api/jobs/{job['id']}").json()["result"] == {
        "pages": 0,
        "blocks": 0,
        "pixels": 0,
        "inpainted": 0,
    }


def fake_letters(image):
    """Slova oblačića „nađena" bez modela (za poslove čišćenja na praznoj probnoj strani)."""
    return fake_mask(Image.fromarray(image))


def fake_mask(image):
    width, height = image.size
    probability = np.zeros((height, width), dtype=np.float32)
    probability[120:160, 150:250] = 0.9
    return probability


def test_bubble_shape_follows_the_white_area_around_the_text():
    gray = np.zeros((300, 400), dtype=np.uint8)
    yy, xx = np.ogrid[:300, :400]
    gray[((xx - 200) / 150) ** 2 + ((yy - 150) / 90) ** 2 <= 1] = 255  # beli oblačić (elipsa)
    gray[100:200, 290:400] = 0  # kosa lika zaseca desnu stranu oblačića

    shape = bubble_shape(gray, (120, 120, 160, 60))

    rows = {int(y): x for x, y in shape[: len(shape) // 2]}
    right = {int(y): x for x, y in shape[len(shape) // 2 :]}
    middle = min(rows, key=lambda row: abs(row - 150))
    assert rows[middle] == 50 and right[middle] == 289  # levo do ivice elipse, desno do kose
    assert min(rows) > 60 and max(rows) < 240  # vertikalno samo unutar oblačića


def test_shape_follows_a_stepped_caption_box():
    """Traka naracije je puna širina gore, a dole ostaje samo levi deo (desno je crtež)."""
    image = np.zeros((300, 400), dtype=np.uint8)
    image[40:120, 20:380] = 255  # gornji deo trake
    image[120:170, 20:150] = 255  # donji, uži deo
    box = (30, 50, 340, 100)

    shape = bubble_shape(image, box)

    rows = {point[1]: point[0] for point in shape[: len(shape) // 2]}
    rights = {point[1]: point[0] for point in shape[len(shape) // 2 :]}
    assert min(rows) < 45 and max(rows) > 160  # oblik ide i ispod stepenika
    assert rights[100.0] > 370 and rights[160.0] < 160


def test_shape_follows_a_bubble_that_a_figure_narrows_at_the_start():
    """Lik zaseca oblačić baš u redu iz kog merenje kreće (Ramon 12, str. 47).

    Ranije se merenje tu zaustavljalo, jer je oblačić iznad šešira naglo širi od početnog reda,
    pa je slagač dobijao samo tanku traku umesto celog oblačića.
    """
    image = np.zeros((400, 400), dtype=np.uint8)
    image[60:340, 60:340] = 255  # oblačić
    image[180:220, 240:340] = 0  # šešir lika ulazi u oblačić baš u sredini
    box = (80, 120, 240, 160)

    shape = bubble_shape(image, box)

    ys = [point[1] for point in shape]
    assert min(ys) < 100 and max(ys) > 300  # ceo oblačić, a ne samo pojas kod šešira


def test_shape_does_not_leak_out_of_the_bubble():
    """Ispod oblačića je beo papir; oblik tu staje, umesto da se proširi na celu stranicu."""
    image = np.zeros((300, 400), dtype=np.uint8)
    image[200:300, :] = 255  # papir ispod oblačića
    image[100:190, 120:280] = 255  # oblačić
    image[190:200, :] = 0  # ivica oblačića

    shape = bubble_shape(image, (130, 120, 140, 50))

    assert max(point[1] for point in shape) < 200


def test_bubble_shape_needs_white_center():
    gray = np.zeros((100, 100), dtype=np.uint8)

    assert bubble_shape(gray, (20, 20, 40, 40)) is None


def test_add_stroke_covers_with_surrounding_color_and_erase_restores():
    original = np.full((100, 100), 240, dtype=np.uint8)
    original[40:50, 40:50] = 0  # zaostala mrlja teksta
    original[80:90, 10:20] = 0  # crtež koji je čišćenje greškom prekrilo
    cleaned = original.copy()
    cleaned[80:90, 10:20] = 240
    covered = np.zeros((100, 100), dtype=bool)
    covered[80:90, 10:20] = True

    strokes = [Stroke("add", 8, [(45, 45)]), Stroke("erase", 8, [(15, 85)])]
    result, mask = apply_strokes(original, cleaned, covered, strokes)

    assert (result[40:50, 40:50] == 240).all() and mask[45, 45]
    assert (result[80:90, 10:20] == 0).all() and not mask[85, 15]


def test_mask_endpoint_updates_clean_image(client, monkeypatch):
    monkeypatch.setattr(cleaning, "text_mask", lambda image, path: fake_mask(image))
    monkeypatch.setattr(cleaning, "ink_letters", lambda image, blocks: fake_letters(image))
    page = create_page(client)
    assert client.post(f"/api/pages/{page['id']}/mask", json={"strokes": []}).status_code == 422

    edited = client.post(
        f"/api/pages/{page['id']}/mask",
        json={"strokes": [{"mode": "add", "radius": 10, "points": [[50, 50], [80, 60]]}]},
    )

    assert edited.status_code == 200 and edited.json()["cleaned_at"] is not None
    assert client.get(f"/api/pages/{page['id']}/clean-image").status_code == 200


def test_dark_background_under_title():
    gray = np.full((100, 200), 240, dtype=np.uint8)
    gray[:, 100:] = 10  # desno crna traka naslova

    assert dark_background(gray, (120, 10, 60, 60)) is True
    assert dark_background(gray, (10, 10, 60, 60)) is False


def test_letters_in_a_balloon_are_found_without_a_model():
    """Slova su tamni delovi unutar okvira koji ne dodiruju ivicu; ivica oblačića i rep ostaju."""
    image, _ = bubble_page()
    image[60:140, 60:62] = 0  # rep oblačića prolazi kroz okvir teksta (od ivice do ivice)

    letters = cleaning.ink_letters(image, [("speech", (95, 85, 110, 30)), ("sfx", (0, 0, 50, 50))])

    assert letters[100, 150] == 1  # tekst
    assert letters[41, 150] == 0 and letters[100, 61] == 0  # ivica oblačića, rep
    assert letters[:50, :50].sum() == 0  # onomatopeje se ovde ne traže


def test_cleaning_works_without_the_optional_text_model(client, tmp_path):
    """Bez neobaveznog modela za onomatopeje oblačići se čiste kao i inače (maska bez modela)."""
    client.app.state.settings.models_dir = str(tmp_path / "prazno")
    page = create_page(client)
    body = {"x": 100, "y": 100, "width": 200, "height": 80, "text": "CIAO", "kind": "speech"}
    client.post(f"/api/pages/{page['id']}/blocks", json=body)

    job = client.post(f"/api/pages/{page['id']}/clean").json()
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)

    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"


def test_covered_sound_effect_is_not_erased(client, monkeypatch):
    """„Prekrij original": onomatopeja ostaje na očišćenoj strani (nova slova je prekrivaju)."""
    erased = []
    monkeypatch.setattr(cleaning, "inpaint", lambda image, mask, models: erased.append(1) or image)
    page = create_page(client)
    body = {"x": 100, "y": 100, "width": 200, "height": 80, "text": "SWACK", "kind": "sfx"}
    block = client.post(f"/api/pages/{page['id']}/blocks", json=body).json()
    client.patch(
        f"/api/blocks/{block['id']}", json={"translation": "SCVAK", "style": {"cover": True}}
    )

    client.post(f"/api/pages/{page['id']}/clean")
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)

    assert erased == []


def test_clean_only_one_block_keeps_the_rest_and_undo_restores(client, settings):
    from pathlib import Path

    from app.models import Page

    page = create_page(client)
    with client.app.state.session_factory() as session:
        path = Path(settings.data_dir) / session.get(Page, page["id"]).image_path
    picture = Image.new("L", (600, 800), 250)  # dva oblačića sa „tekstom"
    picture.paste(20, (120, 120, 280, 140))
    picture.paste(20, (120, 420, 280, 440))
    picture.save(path, "JPEG", quality=95)
    first, second = (
        client.post(
            f"/api/pages/{page['id']}/blocks",
            json={"x": 100, "y": y, "width": 200, "height": 60, "text": "CIAO", "kind": "speech"},
        ).json()
        for y in (100, 400)
    )

    assert client.post(f"/api/blocks/{first['id']}/clean").status_code == 200

    def clean_pixel(x, y):
        with Image.open(
            io.BytesIO(client.get(f"/api/pages/{page['id']}/clean-image").content)
        ) as image:
            return image.convert("L").getpixel((x, y))

    assert clean_pixel(200, 130) > 200  # prvi blok je očišćen
    assert clean_pixel(200, 430) < 60  # drugi nije
    client.post(f"/api/pages/{page['id']}/undo")
    assert clean_pixel(200, 130) < 60  # Poništi vraća original ispod prvog bloka
    assert second["id"] != first["id"]
