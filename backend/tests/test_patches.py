import io

from factories import create_page
from PIL import Image


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
    assert restored["url"] == f"/api/patches/{patch['id']}/image"
