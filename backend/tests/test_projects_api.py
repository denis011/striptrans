from pathlib import Path

from factories import jpeg_bytes, zip_bytes

from worker.main import run_once


def create_project(client, **fields) -> dict:
    response = client.post("/api/projects", json={"series_id": 1, "issue_number": "12", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def import_zip(client, project_id, names, kind="original") -> dict:
    archive = zip_bytes([(name, jpeg_bytes(value=i * 20)) for i, name in enumerate(names)])
    response = client.post(
        f"/api/projects/{project_id}/imports",
        data={"kind": kind},
        files=[("files", ("ramon.cbr", archive, "application/octet-stream"))],
    )
    assert response.status_code == 202, response.text
    state = client.app.state
    assert run_once(state.session_factory, "w1", state.settings) is True
    return client.get(f"/api/jobs/{response.json()['id']}").json()


def pages(client, project_id, kind="original") -> list[dict]:
    return client.get(f"/api/projects/{project_id}/pages", params={"kind": kind}).json()


def test_ramon_series_is_seeded(client):
    assert [series["name"] for series in client.get("/api/series").json()] == ["Italijanski strip"]


def test_duplicate_series_is_rejected(client):
    assert client.post("/api/series", json={"name": "Tex"}).status_code == 201
    assert client.post("/api/series", json={"name": "Tex"}).status_code == 409


def test_project_crud(client):
    project = create_project(client, original_title="Passacro!")
    assert project["series"]["name"] == "Italijanski strip"
    assert project["page_count"] == 0

    updated = client.patch(f"/api/projects/{project['id']}", json={"translated_title": "Pasakr"})
    assert (updated.json()["original_title"], updated.json()["translated_title"]) == (
        "Passacro!",
        "Pasakr",
    )
    assert [p["id"] for p in client.get("/api/projects").json()] == [project["id"]]

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_project_with_unknown_series_is_rejected(client):
    assert client.post("/api/projects", json={"series_id": 999}).status_code == 400


def test_import_through_api(client):
    project = create_project(client)

    job = import_zip(client, project["id"], ["100.jpg", "001.jpg", "002.jpg"])

    assert job["status"] == "done", job["error"]
    assert job["progress"] == job["total"] == 3
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert [p["source_name"] for p in detail["pages"]] == [
        "ramon.cbr/001.jpg",
        "ramon.cbr/002.jpg",
        "ramon.cbr/100.jpg",
    ]
    assert detail["cover_page_id"] == detail["pages"][0]["id"]
    assert detail["jobs"][0]["id"] == job["id"]
    image = client.get(f"/api/pages/{detail['cover_page_id']}/image")
    assert image.headers["content-type"] == "image/jpeg"
    assert "immutable" in image.headers["cache-control"]
    thumbnail = client.get(f"/api/pages/{detail['cover_page_id']}/thumbnail")
    assert thumbnail.headers["content-type"] == "image/webp"


def test_import_rejects_unknown_kind(client):
    project = create_project(client)
    response = client.post(
        f"/api/projects/{project['id']}/imports",
        data={"kind": "prevod"},
        files=[("files", ("a.jpg", jpeg_bytes(), "image/jpeg"))],
    )
    assert response.status_code == 422


def test_reference_pages_are_separate(client):
    project = create_project(client)
    import_zip(client, project["id"], ["1.jpg", "2.jpg"])
    import_zip(client, project["id"], ["1.jpg"], kind="reference")

    detail = client.get(f"/api/projects/{project['id']}").json()

    assert (detail["page_count"], detail["reference_page_count"]) == (2, 1)
    assert [p["position"] for p in pages(client, project["id"], "reference")] == [1]


def test_reorder_pages(client):
    project = create_project(client)
    import_zip(client, project["id"], ["1.jpg", "2.jpg", "3.jpg"])
    ids = [p["id"] for p in pages(client, project["id"])]
    url = f"/api/projects/{project['id']}/pages/order"

    response = client.put(url, json={"kind": "original", "page_ids": ids[::-1]})

    assert [p["id"] for p in response.json()] == ids[::-1]
    assert [p["id"] for p in pages(client, project["id"])] == ids[::-1]
    assert client.put(url, json={"kind": "original", "page_ids": ids[:2]}).status_code == 400


def test_delete_page_renumbers_and_removes_files(client, settings):
    project = create_project(client)
    import_zip(client, project["id"], ["1.jpg", "2.jpg", "3.jpg"])
    before = pages(client, project["id"])
    image_dir = Path(settings.data_dir, "projects", str(project["id"]), "original")

    assert client.delete(f"/api/pages/{before[0]['id']}").status_code == 204

    after = pages(client, project["id"])
    assert [(p["id"], p["position"]) for p in after] == [(before[1]["id"], 1), (before[2]["id"], 2)]
    assert len(list(image_dir.iterdir())) == 2


def test_delete_project_removes_files(client, settings):
    project = create_project(client)
    import_zip(client, project["id"], ["1.jpg"])
    project_dir = Path(settings.data_dir, "projects", str(project["id"]))
    assert project_dir.exists()

    client.delete(f"/api/projects/{project['id']}")

    assert not project_dir.exists()


def test_reset_order_restores_import_order_for_all_kinds(client):
    project = create_project(client)
    import_zip(client, project["id"], ["1.jpg", "2.jpg", "3.jpg"])
    import_zip(client, project["id"], ["1.jpg", "2.jpg"], kind="reference")
    base = f"/api/projects/{project['id']}/pages"
    original = [p["id"] for p in pages(client, project["id"])]
    reference = [p["id"] for p in pages(client, project["id"], "reference")]
    client.put(f"{base}/order", json={"kind": "original", "page_ids": original[::-1]})
    client.put(f"{base}/order", json={"kind": "reference", "page_ids": reference[::-1]})

    response = client.post(f"{base}/reset-order")

    assert response.status_code == 200
    assert [p["id"] for p in pages(client, project["id"])] == original
    assert [p["id"] for p in pages(client, project["id"], "reference")] == reference


def test_import_after_reorder_continues_import_order(client):
    project = create_project(client)
    import_zip(client, project["id"], ["1.jpg", "2.jpg"])
    ids = [p["id"] for p in pages(client, project["id"])]
    order_url = f"/api/projects/{project['id']}/pages/order"
    client.put(order_url, json={"kind": "original", "page_ids": ids[::-1]})

    import_zip(client, project["id"], ["3.jpg"])

    result = pages(client, project["id"])
    assert [(p["position"], p["import_order"]) for p in result] == [(1, 2), (2, 1), (3, 3)]


def test_project_progress_counts_steps_without_skipped_pages(client):
    from factories import create_page

    page = create_page(client)
    block = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 10, "y": 10, "width": 100, "height": 40, "text": "CIAO", "kind": "speech"},
    ).json()
    client.patch(f"/api/blocks/{block['id']}", json={"translation": "zdravo"})
    client.patch(f"/api/pages/{page['id']}", json={"translation_reviewed": True})

    progress = client.get("/api/projects/1").json()["progress"]

    assert progress["pages"] == 1 and progress["skipped"] == []
    assert progress["with_blocks"] == 1 and progress["blocks"] == 1
    assert progress["translation"] == {"edited": 1}
    assert progress["proofread"] == 1 and progress["cleaned"] == 0
    assert progress["exported_at"] is None

    client.patch(f"/api/pages/{page['id']}", json={"skip": True})
    skipped = client.get("/api/projects/1").json()["progress"]

    assert skipped["pages"] == 0 and skipped["skipped"] == [1]
    assert skipped["blocks"] == 0


def test_progress_knows_when_the_album_changed(client):
    from factories import create_page

    page = create_page(client)
    assert client.get("/api/projects/1").json()["progress"]["changed_at"] is None

    client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 10, "y": 10, "width": 100, "height": 40, "text": "CIAO", "kind": "speech"},
    )

    assert client.get("/api/projects/1").json()["progress"]["changed_at"] is not None


def test_reshape_job_measures_bubble_shapes_again(client, monkeypatch):
    """Dugme „Ponovo izmeri oblačiće": oblik se osvežava iz očišćene strane."""
    import io
    import zipfile

    import numpy as np
    from PIL import Image

    from app.services import cleaning

    monkeypatch.setattr(
        cleaning, "text_mask", lambda image, path: np.zeros(np.asarray(image).shape[:2], np.float32)
    )
    page_image = Image.new("L", (400, 400), 0)
    page_image.paste(255, (60, 60, 340, 340))  # beo oblačić na crnoj podlozi
    buffer = io.BytesIO()
    page_image.save(buffer, "PNG")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("1.png", buffer.getvalue())
    project = create_project(client)
    client.post(
        f"/api/projects/{project['id']}/imports",
        data={"kind": "original"},
        files=[("files", ("a.cbz", archive.getvalue(), "application/zip"))],
    )
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)
    page = pages(client, project["id"])[0]
    block = client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"x": 150, "y": 120, "width": 100, "height": 60, "text": "CIAO", "kind": "speech"},
    ).json()
    client.post(f"/api/pages/{page['id']}/clean")
    run_once(state.session_factory, "w1", state.settings)
    measured = client.get(f"/api/pages/{page['id']}/blocks").json()[0]["bubble_polygon"]
    assert measured  # oblik je izmeren pri čišćenju

    # blok je posle čišćenja pomeren, pa je zapamćen oblik zastareo
    client.patch(f"/api/blocks/{block['id']}", json={"y": 220})
    answer = client.post(f"/api/projects/{project['id']}/shapes")
    assert answer.status_code == 202
    run_once(state.session_factory, "w1", state.settings)

    job = client.get(f"/api/jobs/{answer.json()['id']}").json()
    assert job["status"] == "done" and job["result"] == {"pages": 1, "blocks": 1}
    again = client.get(f"/api/pages/{page['id']}/blocks").json()[0]["bubble_polygon"]
    assert again != measured
    history = client.get(f"/api/pages/{page['id']}/history").json()
    assert history["undo"] == "ponovno merenje oblačića"
