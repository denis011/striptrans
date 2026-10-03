import io
from pathlib import Path

from factories import create_page
from PIL import Image

from app.models import Page


def png_bytes(size=(40, 30), color=(200, 30, 30, 255)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def upload(client, page, data=None, **box) -> dict:
    return client.post(
        f"/api/pages/{page['id']}/patches",
        data={key: str(value) for key, value in box.items()},
        files=[("file", ("zakrpa.png", data or png_bytes(), "image/png"))],
    ).json()


def test_patch_lands_in_the_middle_of_the_page_in_its_own_size(client):
    page = create_page(client)  # 600 × 800

    patch = upload(client, page)

    assert (patch["width"], patch["height"]) == (40, 30)
    assert (patch["x"], patch["y"]) == (280, 385)
    assert patch["opacity"] == 1 and patch["above_text"] is False
    assert client.get(patch["url"]).status_code == 200
    assert client.get(f"/api/pages/{page['id']}/patches").json() == [patch]


def test_big_patch_is_fitted_to_the_page(client):
    page = create_page(client)

    patch = upload(client, page, png_bytes(size=(1200, 400)))

    assert (patch["width"], patch["height"]) == (600, 200)


def test_patch_is_moved_and_deleted(client):
    page = create_page(client)
    patch = upload(client, page)

    moved = client.patch(
        f"/api/patches/{patch['id']}", json={"x": 10, "y": 20, "opacity": 0.5, "above_text": True}
    ).json()

    assert (moved["x"], moved["y"], moved["opacity"], moved["above_text"]) == (10, 20, 0.5, True)
    assert client.delete(f"/api/patches/{patch['id']}").status_code == 204
    assert client.get(f"/api/pages/{page['id']}/patches").json() == []


def test_a_file_that_is_not_an_image_is_rejected(client):
    page = create_page(client)

    answer = client.post(
        f"/api/pages/{page['id']}/patches",
        files=[("file", ("tekst.png", b"ovo nije slika", "image/png"))],
    )

    assert answer.status_code == 400 and "slika" in answer.json()["detail"]


def test_undo_brings_a_deleted_patch_back(client):
    page = create_page(client)
    patch = upload(client, page, x=10, y=20, width=100, height=50)
    client.delete(f"/api/patches/{patch['id']}")

    step = client.post(f"/api/pages/{page['id']}/undo").json()

    assert step["action"] == "brisanje zakrpe"
    restored = client.get(f"/api/pages/{page['id']}/patches").json()
    assert restored == [patch]
    assert client.get(patch["url"]).status_code == 200


def test_crop_returns_the_asked_piece_of_the_page(client):
    page = create_page(client)

    answer = client.get(
        f"/api/pages/{page['id']}/crop", params={"x": 5, "y": 6, "width": 70, "height": 40}
    )

    assert answer.status_code == 200
    with Image.open(io.BytesIO(answer.content)) as piece:
        assert piece.size == (70, 40)
    assert "attachment" in answer.headers["content-disposition"]


def test_crop_outside_the_page_is_clamped(client):
    page = create_page(client)

    answer = client.get(
        f"/api/pages/{page['id']}/crop", params={"x": 590, "y": 0, "width": 200, "height": 50}
    )

    with Image.open(io.BytesIO(answer.content)) as piece:
        assert piece.size == (10, 50)


def test_deleting_the_page_removes_the_patch_files(client, settings):
    from pathlib import Path

    page = create_page(client)
    upload(client, page)
    folder = Path(settings.data_dir, "projects", "1", "patches")
    assert list(folder.iterdir())

    client.delete(f"/api/pages/{page['id']}")

    assert not list(folder.iterdir())


def alpha_at(client, patch, x, y) -> int:
    with Image.open(io.BytesIO(client.get(patch["url"]).content)) as image:
        return image.convert("RGBA").getpixel((x, y))[3]


def brush(client, patch, mode, points, radius=5):
    body = {"strokes": [{"mode": mode, "radius": radius, "points": points}]}
    return client.post(f"/api/patches/{patch['id']}/mask", json=body)


def test_brush_hides_and_shows_part_of_the_patch(client):
    page = create_page(client)
    # slika 40 × 30 razvučena na 80 × 60 stranice: potez u stranici je dvostruko manji u slici
    patch = upload(client, page, x=100, y=100, width=80, height=60)

    hidden = brush(client, patch, "hide", [[120, 120]]).json()

    assert hidden["url"] != patch["url"]  # nova verzija slike
    assert alpha_at(client, hidden, 10, 10) == 0  # (120, 120) stranice = (10, 10) slike
    assert alpha_at(client, hidden, 35, 25) == 255
    shown = brush(client, hidden, "show", [[120, 120]], radius=10).json()
    assert alpha_at(client, shown, 10, 10) == 255


def test_brush_follows_patch_rotation_and_undo_restores(client):
    page = create_page(client)
    patch = upload(client, page, x=200, y=200, width=40, height=30)
    client.patch(f"/api/patches/{patch['id']}", json={"rotation": 90})
    # zakrpa okrenuta 90° oko gornjeg levog ugla: piksel slike (5, 10) je na stranici (190, 205)
    hidden = brush(client, patch, "hide", [[190, 205]], radius=2).json()
    assert alpha_at(client, hidden, 5, 10) == 0
    assert alpha_at(client, hidden, 30, 10) == 255

    client.post(f"/api/pages/{page['id']}/undo")
    [restored] = client.get(f"/api/pages/{page['id']}/patches").json()
    assert restored["url"] == patch["url"]  # bez maske, ista slika kao pre poteza


def test_patch_for_a_block_is_gray_on_a_gray_page(client, settings):
    page = create_page(client)  # JPEG strana iz fabrike je u boji
    data_dir = Path(settings.data_dir)
    with client.app.state.session_factory() as session:
        stored = session.get(Page, page["id"])
        path = data_dir / stored.image_path
        white = Image.new("L", (600, 800), 250)  # crno-bela strana: beo papir i stara slova u bloku
    white.paste(20, (130, 130, 270, 150))
    white.save(path, "JPEG", quality=95)
    patch = upload(
        client, page, x=10, y=20, width=100, height=50, match_page="true", above_text="true"
    )

    assert (patch["x"], patch["y"], patch["width"], patch["height"]) == (10, 20, 100, 50)
    assert patch["above_text"] is True
    with Image.open(io.BytesIO(client.get(patch["url"]).content)) as image:
        assert image.mode == "LA"


def test_ai_prompt_for_manual_work(client):
    page = create_page(client)
    block = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 10, "y": 10, "width": 100, "height": 40, "text": "CRASH!"},
    ).json()
    assert client.get(f"/api/blocks/{block['id']}/ai-prompt").status_code == 400
    client.patch(f"/api/blocks/{block['id']}", json={"kind": "sfx", "translation": "KRAŠ!"})

    prompt = client.get(f"/api/blocks/{block['id']}/ai-prompt").json()["prompt"]

    assert '"CRASH!"' in prompt and '"KRAŠ!"' in prompt and "K-R-A-Š" in prompt


def test_new_patch_after_a_deleted_one_gets_a_new_address(client):
    page = create_page(client)
    first = upload(client, page)
    client.delete(f"/api/patches/{first['id']}")
    second = upload(client, page, png_bytes(color=(0, 0, 255, 255)))

    assert second["id"] != first["id"]  # AUTOINCREMENT: broj obrisane zakrpe se ne ponavlja
    assert second["url"] != first["url"]  # a adresa ionako zavisi i od fajla


def test_ai_app_image_on_a_block_is_fitted_leveled_and_cleaned(client, settings):
    page = create_page(client)  # 600 × 800
    data_dir = Path(settings.data_dir)
    with client.app.state.session_factory() as session:
        path = data_dir / session.get(Page, page["id"]).image_path
    white = Image.new("L", (600, 800), 250)  # crno-bela strana: beo papir i stara slova u bloku
    white.paste(20, (130, 130, 270, 150))
    white.save(path, "JPEG", quality=95)
    block = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 100, "y": 100, "width": 200, "height": 80, "text": "SWISH"},
    ).json()
    # „Gemini": isečak bloka + 10 px (220 × 100), bež papir, nova slova u bloku, izmišljena mrlja
    # u uglu van natpisa; vraćen u manjoj rezoluciji
    proposal = Image.new("L", (220, 100), 215)
    for x in range(40, 180, 30):
        proposal.paste(30, (x, 40, x + 15, 70))  # nova slova
    proposal.paste(30, (0, 0, 6, 6))  # izmišljeno, van okvira bloka i odvojeno od slova
    small = proposal.resize((176, 80))
    buffer = io.BytesIO()
    small.save(buffer, "PNG")

    patch = client.post(
        f"/api/pages/{page['id']}/patches",
        data={"block_id": str(block["id"])},
        files=[("file", ("gemini.png", buffer.getvalue(), "image/png"))],
    ).json()

    assert patch["above_text"] is True
    with Image.open(io.BytesIO(client.get(patch["url"]).content)) as image:
        image = image.convert("LA")
        at = lambda x, y: image.getpixel((round(x - patch["x"]), round(y - patch["y"])))  # noqa: E731
        assert at(150, 165)[0] > 235  # bež papir je postao beo kao stranica
        assert at(137, 145)[0] < 90 and at(137, 145)[1] == 255  # nova slova su tu
    # mrlja u uglu isečka (90, 90) nije preneta: zakrpa je ne pokriva ili je tu providna
    covered = patch["x"] <= 92 and patch["y"] <= 92
    if covered:
        with Image.open(io.BytesIO(client.get(patch["url"]).content)) as image:
            assert image.convert("LA").getpixel((92 - patch["x"], 92 - patch["y"]))[1] < 40
