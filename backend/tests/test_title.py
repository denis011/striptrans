"""Naslov od slova originala (Faza 6a): isecanje, dopuna slova koja nedostaju, čišćenje, API."""

import io
import json
from pathlib import Path

import cv2
import numpy as np
from factories import zip_bytes
from PIL import Image, ImageDraw, ImageFont

from app.services import cleaning, title
from app.services.fonts import BUILTIN_DIR
from app.services.title import CHARSET, complete, find_letters, max_scale
from worker.main import run_once

BOX = (40, 70, 820, 170)  # okvir naslova na probnoj strani


def title_image(text="PASSACRO!", light=True, bar=(40, 259)) -> Image.Image:
    """Traka sa naslovom: bela slova na crnom (ili tamna na svetlom), slova se ne dodiruju."""
    image = Image.new("L", (900, 300), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, bar[0], 899, bar[1]), fill=0 if light else 230)
    font = ImageFont.truetype(str(BUILTIN_DIR / "Bangers-Regular.ttf"), 120)
    x = 60
    for char in text:
        draw.text((x, 90), char, font=font, fill=255 if light else 0)
        x += font.getlength(char) + 10
    return image


def gray(image: Image.Image) -> np.ndarray:
    return np.asarray(image)


def test_letters_are_cut_and_labeled_with_the_original_text():
    letters = find_letters(gray(title_image()), BOX, "PASSACRO!")

    assert [g.char for g in letters.glyphs] == list("PASSACRO!")
    assert letters.light and letters.uniform and not letters.mismatch
    exclamation = letters.glyphs[-1]  # crta i tačka su jedno slovo
    assert exclamation.alpha.shape[0] > 0.9 * letters.cap_height
    assert letters.glyphs[0].alpha.max() == 255  # neprovidno slovo, meka ivica


def test_dark_letters_on_light_background():
    letters = find_letters(gray(title_image(light=False)), BOX, "PASSACRO!")

    assert not letters.light and len(letters.glyphs) == 9


def test_interlocking_letters_stay_separate_and_keep_their_gap():
    image = Image.new("L", (400, 200), 0)
    draw = ImageDraw.Draw(image)
    draw.rectangle((50, 40, 170, 60), fill=255)  # „Γ": gornja greda prelazi preko sledećeg slova
    draw.rectangle((50, 40, 70, 160), fill=255)
    draw.rectangle((120, 80, 140, 160), fill=255)  # „L" ispod grede
    draw.rectangle((120, 140, 220, 160), fill=255)

    letters = find_letters(np.asarray(image), (30, 30, 220, 140), "TL")

    assert [g.char for g in letters.glyphs] == ["T", "L"]
    assert letters.glyphs[0].gap_next < 0  # okviri se preklapaju


def test_broken_letter_is_joined_when_the_text_has_fewer_letters():
    image = Image.new("L", (300, 300), 0)
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 40, 140, 140), fill=255)  # slovo I prelomljeno na dva velika dela
    draw.rectangle((104, 150, 136, 250), fill=255)

    letters = find_letters(np.asarray(image), (80, 30, 90, 240), "I")

    assert len(letters.glyphs) == 1 and not letters.mismatch


def test_letter_count_mismatch_is_reported():
    letters = find_letters(gray(title_image()), BOX, "MASACRO!")

    assert letters.mismatch and len(letters.glyphs) == 9 and letters.expected == 8


def test_missing_letters_are_made_to_match_the_original():
    letters = find_letters(gray(title_image()), BOX, "PASSACRO!")
    complete(letters)

    extra = {g.char: g for g in letters.extra}
    assert set(extra) | {g.char for g in letters.glyphs} == set(CHARSET)
    assert extra["K"].source == "fallback"
    k_height = np.flatnonzero((extra["K"].alpha > 127).any(axis=1))
    assert abs((k_height[-1] - k_height[0] + 1) - letters.cap_height) < 0.15 * letters.cap_height
    s = next(g for g in letters.glyphs if g.char == "S")
    assert extra["Š"].source == "accent"  # S originala + kvačica
    assert extra["Š"].alpha.shape[0] > s.alpha.shape[0]
    assert extra["Š"].baseline > s.baseline  # slovo ostaje na istoj osnovnoj liniji


def test_new_letters_have_scan_like_soft_edges():
    """Slovo se crta uvećano pa smanjuje: ivica ima prelaz kao na skenu, bez stepenica."""
    letters = find_letters(gray(title_image()), BOX, "PASSACRO!")
    complete(letters)

    made = next(g for g in letters.extra if g.char == "K")
    original = next(g for g in letters.glyphs if g.char == "R")

    def edge(alpha):  # udeo prelaznih piksela po pikselu konture
        solid = (alpha > 127).astype(int)
        border = np.abs(np.diff(solid, axis=1)).sum() + np.abs(np.diff(solid, axis=0)).sum()
        return ((alpha > 25) & (alpha < 230)).sum() / max(border, 1)

    assert edge(made.alpha) > 0.5 * edge(original.alpha)
    assert set(np.unique(made.alpha)) - {0, 255}  # nije samo puno/prazno


def test_title_may_grow_only_as_much_as_the_bar_allows():
    roomy = find_letters(gray(title_image()), BOX, "PASSACRO!")
    tight = find_letters(gray(title_image(bar=(98, 207))), BOX, "PASSACRO!")

    assert max_scale(roomy) > max_scale(tight) >= 1


def upload_page(client, image: Image.Image) -> dict:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    project = client.post("/api/projects", json={"series_id": 1}).json()
    client.post(
        f"/api/projects/{project['id']}/imports",
        data={"kind": "original"},
        files=[("files", ("a.cbz", zip_bytes([("1.png", buffer.getvalue())]), "application/zip"))],
    )
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)
    return client.get(f"/api/projects/{project['id']}/pages").json()[0]


def title_block(client, page: dict, **changes) -> dict:
    x, y, w, h = BOX
    block = {"x": x, "y": y, "width": w, "height": h, "text": "PASSACRO!", "kind": "other"}
    created = client.post(f"/api/pages/{page['id']}/blocks", json=block).json()
    return client.patch(f"/api/blocks/{created['id']}", json={"kind": "title", **changes}).json()


def test_switching_to_title_cuts_the_letters(client):
    page = upload_page(client, title_image())

    block = title_block(client, page)

    assert block["title"]["found"] == 9 and block["title"]["expected"] == 9
    assert [g["char"] for g in block["title"]["glyphs"]] == list("PASSACRO!")
    glyph = client.get(f"/api/blocks/{block['id']}/glyphs/g0.png")
    assert glyph.status_code == 200 and glyph.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(glyph.content)).mode == "LA"
    assert client.get(f"/api/blocks/{block['id']}/glyphs/g99.png").status_code == 404

    other = client.patch(f"/api/blocks/{block['id']}", json={"kind": "other"}).json()
    assert other["title"] is None
    assert client.get(f"/api/blocks/{block['id']}/glyphs/g0.png").status_code == 404


def test_new_text_cuts_a_new_version(client):
    page = upload_page(client, title_image())
    block = title_block(client, page)

    changed = client.patch(f"/api/blocks/{block['id']}", json={"text": "PASSACRO !"}).json()
    again = client.post(f"/api/blocks/{block['id']}/title").json()

    assert changed["title"]["version"] != block["title"]["version"]
    assert again["title"]["version"] != changed["title"]["version"]
    assert changed["title"]["glyphs"][-1]["space_before"]


def clean_image(client, page: dict) -> np.ndarray:
    response = client.get(f"/api/pages/{page['id']}/clean-image")
    return np.asarray(Image.open(io.BytesIO(response.content)).convert("L"))


def test_cleaning_erases_the_title_only_when_translated(client, monkeypatch):
    monkeypatch.setattr(
        cleaning, "text_mask", lambda image, path: np.zeros(image.size[::-1], np.float32)
    )
    page = upload_page(client, title_image())
    untranslated = title_block(client, page)
    state = client.app.state

    client.post(f"/api/pages/{page['id']}/clean")
    run_once(state.session_factory, "w1", state.settings)
    kept = clean_image(client, page)
    client.patch(f"/api/blocks/{untranslated['id']}", json={"translation": "PASAKR!"})
    client.post(f"/api/pages/{page['id']}/clean")
    run_once(state.session_factory, "w1", state.settings)
    erased = clean_image(client, page)

    x, y, w, h = BOX
    assert kept[y : y + h, x : x + w].max() == 255  # bez prevoda original ostaje
    assert erased[y : y + h, x : x + w].max() < 40  # slova obrisana bojom trake
    block = client.get(f"/api/pages/{page['id']}/blocks").json()[0]
    assert block["title"]["found"] == 9


def test_deleted_block_keeps_its_letters_until_the_page_goes(client, settings):
    page = upload_page(client, title_image())
    block = title_block(client, page)
    project_id = client.get("/api/projects").json()[0]["id"]
    folder = title.title_dir(Path(settings.data_dir), project_id, block["id"])
    assert folder.exists()

    client.delete(f"/api/blocks/{block['id']}")
    assert folder.exists()  # „Poništi" vraća blok sa istim slovima

    client.delete(f"/api/pages/{page['id']}")
    assert not folder.exists()


def drawn_title(
    font_file: str, text="PASSACRO!", size=110, shear=0.0, outline=0, gap=10
) -> np.ndarray:
    """Crno-bela strana sa naslovom datim fontom (po želji koso ili samo kontura slova)."""
    image = Image.new("L", (1000, 300), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(title.FONT_DIR / font_file), size)
    x = 80
    for char in text:
        if outline:
            draw.text((x, 60), char, font=font, fill=255, stroke_width=outline, stroke_fill=0)
        else:
            draw.text((x, 60), char, font=font, fill=0)
        x += font.getlength(char) + gap + 2 * outline
    gray = np.asarray(image)
    if shear:
        matrix = np.float32([[1, -shear, shear * 200], [0, 1, 0]])
        gray = cv2.warpAffine(gray, matrix, (1000, 300), borderValue=255)
    return gray


def test_touching_letters_are_split_at_the_thinnest_place():
    gray = drawn_title("RobotoSerif-CondensedBlack.ttf").copy()
    gray[178:184, 60:900] = 0  # tanka linija spaja sva slova pri dnu, kao spojeni serifi

    letters = find_letters(gray, (60, 40, 880, 200), "PASSACRO!")

    assert "".join(g.char for g in letters.glyphs) == "PASSACRO!"
    assert not letters.mismatch


def test_fallback_font_is_the_one_most_like_the_original():
    serif = find_letters(
        drawn_title("RobotoSerif-CondensedBlack.ttf"), (60, 40, 880, 200), "PASSACRO!"
    )
    sans = find_letters(
        drawn_title("ArchivoBlack-Regular.ttf", size=90), (60, 40, 900, 200), "PASSACRO!"
    )
    complete(serif)
    complete(sans)

    assert serif.font == "Roboto Serif" and sans.font == "Archivo Black"
    # štampana slova su glatka: napravljeno K nema „raščupanu" ivicu
    k = next(g for g in serif.extra if g.char == "K")
    assert title._roughness(title._crop(k.alpha > 127), serif.cap_height) < 1.0


def test_slanted_title_gets_slanted_new_letters():
    letters = find_letters(
        drawn_title("ArchivoBlack-Regular.ttf", size=90, shear=0.2), (60, 40, 930, 200), "PASSACRO!"
    )
    complete(letters)

    assert abs(letters.slant - 0.2) < 0.05
    k = next(g for g in letters.extra if g.char == "K")
    upright = title._slant([k.alpha > 127])
    assert abs(upright - letters.slant) < 0.06


def test_hollow_title_gets_hollow_new_letters():
    gray = drawn_title("ArchivoBlack-Regular.ttf", size=110, outline=4, gap=14)
    letters = find_letters(gray, (60, 30, 930, 230), "PASSACRO!")
    complete(letters)

    assert letters.hollow
    k = next(g for g in letters.extra if g.char == "K").alpha > 127
    assert k.sum() < 0.6 * title._fill_holes(k).sum()  # samo kontura


def glyph_png(width=60, height=90, filled=True) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if filled:
        ImageDraw.Draw(image).rectangle((10, 5, 30, height - 6), fill=(255, 255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_letter_made_of_parts_is_saved_kept_and_deleted(client):
    page = upload_page(client, title_image())
    block = title_block(client, page)
    parts = [{"source": "g6", "polygon": [[0, 0], [30, 0], [30, 90]], "x": 40, "y": 50}]

    def post(**fields):
        data = {"char": "k", "baseline": "84", "parts": json.dumps(parts), **fields}
        files = {"file": ("k.png", glyph_png(), "image/png")}
        return client.post(f"/api/blocks/{block['id']}/glyphs", data=data, files=files)

    saved = post().json()["title"]
    entry = saved["custom"][0]
    assert entry["key"] == "c0" and entry["char"] == "K" and entry["source"] == "custom"
    assert entry["ink_left"] == 10 and entry["ink_right"] == 31 and entry["parts"] == parts
    image = client.get(f"/api/blocks/{block['id']}/glyphs/c0.png")
    assert image.status_code == 200 and Image.open(io.BytesIO(image.content)).mode == "LA"
    assert len(post(key="c0").json()["title"]["custom"]) == 1  # zamena, ne novo slovo

    recut = client.patch(f"/api/blocks/{block['id']}", json={"text": "PASSACRO !"}).json()["title"]
    assert recut["version"] != saved["version"] and recut["custom"][0]["key"] == "c0"
    assert client.get(f"/api/blocks/{block['id']}/glyphs/c0.png").status_code == 200

    deleted = client.delete(f"/api/blocks/{block['id']}/glyphs/c0").json()["title"]
    assert deleted["custom"] == []
    assert client.get(f"/api/blocks/{block['id']}/glyphs/c0.png").status_code == 404
    assert client.delete(f"/api/blocks/{block['id']}/glyphs/c0").status_code == 404


def test_empty_or_unknown_letter_is_rejected(client):
    page = upload_page(client, title_image())
    block = title_block(client, page)
    url = f"/api/blocks/{block['id']}/glyphs"

    empty = client.post(
        url,
        data={"char": "K", "baseline": "80"},
        files={"file": ("k.png", glyph_png(filled=False), "image/png")},
    )
    unknown = client.post(
        url,
        data={"char": "K", "baseline": "80", "key": "c7"},
        files={"file": ("k.png", glyph_png(), "image/png")},
    )
    two = client.post(
        url,
        data={"char": "KK", "baseline": "80"},
        files={"file": ("k.png", glyph_png(), "image/png")},
    )

    assert [r.status_code for r in (empty, unknown, two)] == [400, 400, 400]


def test_hollow_letters_keep_their_paper_fill(client, monkeypatch):
    # bela slova sa crnom konturom preko „crteža" (šrafure): unutrašnjost je ispuna, šrafura nije
    image = Image.new("L", (900, 300), 255)
    draw = ImageDraw.Draw(image)
    for x in range(0, 900, 9):
        draw.line((x, 0, x + 120, 300), fill=0, width=2)
    font = ImageFont.truetype(str(BUILTIN_DIR / "Bangers-Regular.ttf"), 130)
    x = 60
    for char in "CLICK":
        draw.text((x, 70), char, font=font, fill=255, stroke_width=5, stroke_fill=0)
        x += font.getlength(char) + 30
    letters = find_letters(np.asarray(image), (50, 80, 400, 115), "CLICK")

    assert all(glyph.fill is not None for glyph in letters.glyphs)
    c = letters.glyphs[0]
    assert (c.fill > 127).sum() > 1.5 * (c.alpha > 127).sum()  # ispuna je ceo oblik slova
    assert letters.paper > 200
    # čišćenje briše celo slovo (kontura i unutrašnjost), ne samo konturu
    inside = (c.fill > 127) & (c.alpha < 64)
    rows, cols = np.nonzero(inside)
    assert letters.mask[c.box[1] + rows, c.box[0] + cols].all()
    complete(letters)
    b = next(g for g in letters.extra if g.char == "B")  # napravljeno šuplje slovo ima ispunu
    assert b.fill is not None and (b.fill > 127).sum() > (b.alpha > 127).sum()

    monkeypatch.setattr(
        cleaning, "text_mask", lambda image, path: np.zeros(image.size[::-1], np.float32)
    )
    page = upload_page(client, image)
    x0, y0, w, h = (50, 80, 400, 115)
    created = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": x0, "y": y0, "width": w, "height": h, "text": "CLICK", "kind": "title"},
    ).json()
    block = client.patch(f"/api/blocks/{created['id']}", json={"translation": "KLIK"}).json()
    assert block["title"]["glyphs"][0]["fill"] and block["title"]["paper"] > 200
    fill = client.get(f"/api/blocks/{created['id']}/glyphs/g0f.png")
    assert fill.status_code == 200 and Image.open(io.BytesIO(fill.content)).mode == "LA"


def test_letter_made_of_parts_keeps_its_fill(client):
    page = upload_page(client, title_image())
    block = title_block(client, page)
    url = f"/api/blocks/{block['id']}/glyphs"
    data = {"char": "K", "baseline": "84"}

    saved = client.post(
        url,
        data=data,
        files={
            "file": ("k.png", glyph_png(), "image/png"),
            "fill": ("f.png", glyph_png(), "image/png"),
        },
    ).json()["title"]["custom"][0]
    wrong = client.post(
        url,
        data=data,
        files={
            "file": ("k.png", glyph_png(), "image/png"),
            "fill": ("f.png", glyph_png(40, 40), "image/png"),
        },
    )

    assert saved["fill"] is True
    assert client.get(f"/api/blocks/{block['id']}/glyphs/c0f.png").status_code == 200
    assert client.get(f"/api/blocks/{block['id']}/glyphs/g99f.png").status_code == 404
    assert wrong.status_code == 400


def test_hollow_title_over_busy_artwork_keeps_clean_outlines():
    """Šuplja slova preko gustog crteža (str. 5 u 13): nađu se sva, po beloj unutrašnjosti."""
    image = Image.new("L", (1000, 300), 255)
    draw = ImageDraw.Draw(image)
    for offset in range(-300, 1000, 9):  # gusto šrafiranje crteža svuda okolo i između slova
        draw.line((offset, 300, offset + 300, 0), fill=0, width=2)
    font = ImageFont.truetype(str(title.FONT_DIR / "Anton-Regular.ttf"), 180)
    x = 80
    for char in "DUGO":
        draw.text((x, 40), char, font=font, fill=255, stroke_width=10, stroke_fill=0)
        x += font.getbbox(char)[2] + 40
    gray = np.asarray(image)

    letters = find_letters(gray, (60, 30, 880, 240), "DUGO")
    complete(letters)

    assert letters is not None and len(letters.glyphs) == 4
    assert letters.hollow
    assert all(glyph.fill is not None for glyph in letters.glyphs)  # bela unutrašnjost je ispuna
    made = next(g for g in letters.extra if g.char == "S")
    assert made.fill is not None  # napravljeno slovo je takođe šuplje, sa ispunom


def tilted_line(text: str, angle: float, italic: float = 0.0) -> np.ndarray:
    """Crni rukopisni red na beloj traci, nakošen za `angle` stepeni i po želji u kurzivu."""
    font = ImageFont.truetype(str(title.FONT_DIR / "ComicNeue-Bold.ttf"), 40)
    line = Image.new("L", (900, 120), 255)
    ImageDraw.Draw(line).text((40, 40), text, font=font, fill=0)
    array = np.asarray(line)
    if italic:
        shear = np.float32([[1, -italic, italic * 80], [0, 1, 0]])
        array = cv2.warpAffine(array, shear, (900, 120), borderValue=255)
    page = np.full((500, 1000), 255, np.uint8)
    page[190:310, 50:950] = array
    rotation = cv2.getRotationMatrix2D((500.0, 250.0), -angle, 1.0)
    return cv2.warpAffine(page, rotation, (1000, 500), borderValue=255)


def test_tilted_italic_line_is_straightened_before_cutting():
    gray = tilted_line("TESTO E DISEGNI", 9, italic=0.35)

    letters = find_letters(gray, (60, 150, 880, 200), "TESTO E DISEGNI")

    assert letters is not None
    assert 7 < letters.angle < 11  # red se spušta udesno
    assert letters.skew > 0.2  # kurziv je skinut pre sečenja
    assert len(letters.glyphs) == letters.expected == 13
    assert {g.row for g in letters.glyphs} == {0}  # jedan red, ne stepenice
    # maska za čišćenje je pod pravim uglom: prekriva slova na stranici, ne ispravljen red
    ys, xs = np.nonzero(letters.mask)
    left, right = xs.min(), xs.max()
    drift = ys[xs > right - 40].mean() - ys[xs < left + 40].mean()
    assert drift > 0.6 * (right - left - 40) * np.tan(np.radians(9))


def test_upright_title_is_not_rotated():
    letters = find_letters(gray(title_image()), BOX, "PASSACRO!")

    assert letters.angle == 0 and letters.center is None


def test_letters_are_matched_to_text_by_width():
    # oblik širine „DI" nosi dva slova teksta, ostali po jedno
    plan = title._cover([20.0, 26.0, 20.0], ["S", "D", "I", "E"])

    assert plan == [["S"], ["D", "I"], ["E"]]


def test_user_title_fonts_are_fallback_candidates(client, settings, monkeypatch):
    page = upload_page(client, title_image())
    fonts_dir = Path(settings.data_dir, "fonts")
    fonts_dir.mkdir(exist_ok=True)
    (fonts_dir / "naslovi.otf").write_bytes(
        (title.FONT_DIR / "RobotoSerif-CondensedBlack.ttf").read_bytes()
    )
    state = client.app.state
    with state.session_factory() as session:
        from app.models import Font

        session.add(Font(name="Naslovi", path="fonts/naslovi.otf", kind="title"))
        session.add(Font(name="Rukopis", path="fonts/naslovi.otf", kind="dialogue"))
        session.commit()
    seen = []
    original = title.complete
    monkeypatch.setattr(
        title,
        "complete",
        lambda letters, fonts, *rest: seen.append(fonts) or original(letters, fonts, *rest),
    )

    block = title_block(client, page)

    # automatski se bira samo među fontovima za naslove; rukopis se nudi za ručni izbor slova
    assert [name for name, _ in seen[0]] == ["Archivo Black", "Roboto Serif", "Anton", "Naslovi"]
    assert block["title"]["fonts"][-2:] == ["Naslovi", "Rukopis"]


def test_chosen_font_makes_that_letter_and_overrides_the_accent():
    letters = find_letters(gray(title_image()), BOX, "PASSACRO!")
    complete(letters, chosen={"K": "Anton", "Š": "Anton", "Ž": "nepostojeći"})

    extra = {g.char: g for g in letters.extra}
    assert letters.fonts == ["Archivo Black", "Roboto Serif", "Anton"]
    assert (extra["K"].source, extra["K"].font) == ("fallback", "Anton")
    assert (extra["Š"].source, extra["Š"].font) == ("fallback", "Anton")  # ne S sa kvačicom
    assert extra["Ž"].font == letters.font  # nepoznat font: automatski izbor
    assert extra["Z"].font == letters.font


def test_changing_letter_font_cuts_a_new_version(client):
    page = upload_page(client, title_image())
    block = title_block(client, page)

    changed = client.patch(
        f"/api/blocks/{block['id']}", json={"style": {"letter_fonts": {"K": "Anton"}}}
    ).json()
    same = client.patch(
        f"/api/blocks/{block['id']}", json={"style": {"letter_fonts": {"K": "Anton"}, "scale": 1.1}}
    ).json()

    assert changed["title"]["version"] != block["title"]["version"]
    assert same["title"]["version"] == changed["title"]["version"]  # font se nije menjao
    k = next(g for g in changed["title"]["extra"] if g["char"] == "K")
    assert k["font"] == "Anton" and "Anton" in changed["title"]["fonts"]


def test_glyph_keys_and_paths_stay_inside_the_data_folder(tmp_path):
    from app.paths import UnsafePath, inside
    from app.services.title import GLYPH_KEY

    assert all(GLYPH_KEY.fullmatch(key) for key in ("g0", "x12", "c3f"))
    assert not any(GLYPH_KEY.fullmatch(key) for key in ("../x", "g0/../../a", "c", "g0.png"))
    assert inside(tmp_path, "projects", 7) == tmp_path / "projects" / "7"
    for bad in (("..", "etc"), ("projects", "../../etc")):
        try:
            inside(tmp_path, *bad)
        except UnsafePath:
            continue
        raise AssertionError(f"{bad} je prošlo")
