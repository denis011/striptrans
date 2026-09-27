from factories import create_page


def test_undo_and_redo_a_block_edit(client):
    page = create_page(client)
    block = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 10, "y": 10, "width": 100, "height": 50, "text": "CIAO", "kind": "speech"},
    ).json()

    client.patch(f"/api/blocks/{block['id']}", json={"translation": "zdravo"})
    assert client.get(f"/api/pages/{page['id']}/blocks").json()[0]["translation"] == "ZDRAVO"

    step = client.post(f"/api/pages/{page['id']}/undo").json()
    assert step["action"] == "izmena bloka"
    assert step["blocks"][0]["translation"] == ""
    assert step["redo"] == "izmena bloka" and step["undo"] == "nov blok"

    again = client.post(f"/api/pages/{page['id']}/redo").json()
    assert again["blocks"][0]["translation"] == "ZDRAVO"
    assert client.get(f"/api/pages/{page['id']}/history").json()["redo"] is None


def test_undo_brings_a_deleted_block_back(client):
    page = create_page(client)
    block = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 10, "y": 10, "width": 100, "height": 50, "text": "CIAO", "kind": "speech"},
    ).json()
    client.delete(f"/api/blocks/{block['id']}")
    assert client.get(f"/api/pages/{page['id']}/blocks").json() == []

    step = client.post(f"/api/pages/{page['id']}/undo").json()

    assert [b["id"] for b in step["blocks"]] == [block["id"]]
    assert step["blocks"][0]["text"] == "CIAO"


def test_new_change_forgets_the_redo_steps(client):
    page = create_page(client)
    block = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 10, "y": 10, "width": 100, "height": 50, "text": "CIAO", "kind": "speech"},
    ).json()
    client.patch(f"/api/blocks/{block['id']}", json={"text": "PRVI"})
    client.post(f"/api/pages/{page['id']}/undo")
    client.patch(f"/api/blocks/{block['id']}", json={"text": "DRUGI"})

    assert client.get(f"/api/pages/{page['id']}/history").json()["redo"] is None
    assert client.post(f"/api/pages/{page['id']}/redo").json()["action"] is None


def test_history_keeps_only_the_last_steps(client):
    from app.services.history import LIMIT

    page = create_page(client)
    block = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 10, "y": 10, "width": 100, "height": 50, "text": "CIAO", "kind": "speech"},
    ).json()
    for i in range(LIMIT + 5):
        client.patch(f"/api/blocks/{block['id']}", json={"text": f"T{i}"})

    for _ in range(LIMIT):
        assert client.post(f"/api/pages/{page['id']}/undo").json()["action"] is not None
    assert client.post(f"/api/pages/{page['id']}/undo").json()["action"] is None


def test_undo_brings_back_the_pixels_a_brush_stroke_covered(client, monkeypatch):
    import numpy as np

    from app.services import cleaning
    from worker.main import run_once

    def fake_mask(image):
        return np.zeros(np.asarray(image).shape[:2], dtype=np.float32)

    monkeypatch.setattr(cleaning, "text_mask", lambda image, path: fake_mask(image))
    page = create_page(client, noise=True)  # šarena strana: potez četkicom se vidi
    state = client.app.state
    client.post(f"/api/pages/{page['id']}/clean")
    run_once(state.session_factory, "w1", state.settings)
    before = client.get(f"/api/pages/{page['id']}/clean-image").content

    client.post(
        f"/api/pages/{page['id']}/mask",
        json={"strokes": [{"mode": "add", "radius": 10, "points": [[50, 50], [80, 60]]}]},
    )
    assert client.get(f"/api/pages/{page['id']}/clean-image").content != before

    step = client.post(f"/api/pages/{page['id']}/undo").json()

    assert step["action"] == "potez četkicom"
    assert client.get(f"/api/pages/{page['id']}/clean-image").content == before


def test_more_brush_strokes_than_the_history_keeps(client, monkeypatch):
    """Istorija zaboravi najstariji potez četkicom i briše njegov isečak (bila je greška 500)."""
    import numpy as np

    from app.services import cleaning
    from app.services.history import LIMIT
    from worker.main import run_once

    monkeypatch.setattr(
        cleaning,
        "text_mask",
        lambda image, path: np.zeros(np.asarray(image).shape[:2], dtype=np.float32),
    )
    page = create_page(client, noise=True)
    state = client.app.state
    client.post(f"/api/pages/{page['id']}/clean")
    run_once(state.session_factory, "w1", state.settings)
    stroke = {"mode": "add", "radius": 5, "points": [[50, 50], [60, 55]]}

    for mode in ["add"] * (LIMIT + 2) + ["erase"]:  # erase: „vrati original"
        body = {"strokes": [{**stroke, "mode": mode}]}
        assert client.post(f"/api/pages/{page['id']}/mask", json=body).status_code == 200

    # posle poništavanja nov potez briše „Ponovi" (i njegove isečke), bez greške
    client.post(f"/api/pages/{page['id']}/undo")
    body = {"strokes": [stroke]}
    assert client.post(f"/api/pages/{page['id']}/mask", json=body).status_code == 200
    from pathlib import Path

    pieces = list((Path(state.settings.data_dir) / "projects").rglob("history/*.png"))
    assert len(pieces) <= 2 * LIMIT  # isečci zaboravljenih poteza su obrisani
