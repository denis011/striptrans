import io
import zipfile

import pypdfium2 as pdfium
from factories import create_page, jpeg_bytes, zip_bytes
from PIL import Image

from worker.main import run_once


def png(size, color=200) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (color, color, color)).save(buffer, "PNG")
    return buffer.getvalue()


def project_with_pages(client, count=3):
    """Projekat sa `count` sivih stranica 600×800; druga je preskočena (npr. reklama)."""
    create_page(client)
    project_id = client.get("/api/projects").json()[0]["id"]
    for _ in range(count - 1):
        archive = zip_bytes([("x.jpg", jpeg_bytes(size=(600, 800)))])
        client.post(
            f"/api/projects/{project_id}/imports",
            data={"kind": "original"},
            files=[("files", ("a.cbz", archive, "application/zip"))],
        )
        state = client.app.state
        run_once(state.session_factory, "w1", state.settings)
    pages = client.get(f"/api/projects/{project_id}/pages").json()
    client.patch(f"/api/pages/{pages[1]['id']}", json={"skip": True})
    return project_id, pages


def run_worker(client):
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)


def export_album(client, project_id, **settings):
    export = client.post(f"/api/projects/{project_id}/exports", json=settings).json()
    for item in export["pages"]:
        if item["render"]:
            response = client.put(
                f"/api/exports/{export['id']}/pages/{item['position']}",
                content=png((600, 800)),
                headers={"content-type": "image/png"},
            )
            assert response.status_code == 200, response.text
    job = client.post(f"/api/exports/{export['id']}/finish").json()
    run_worker(client)
    return export, client.get(f"/api/jobs/{job['id']}").json()


def test_cbz_contains_pages_in_order_and_comic_info(client):
    project_id, pages = project_with_pages(client)

    export, job = export_album(client, project_id)

    assert [item["render"] for item in export["pages"]] == [
        True,
        False,
        True,
    ]  # preskočena: original
    assert job["status"] == "done", job
    response = client.get(f"/api/exports/{export['id']}/file")
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith(('.cbz"', ".cbz"))
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert names == ["001.jpg", "002.jpg", "003.jpg", "ComicInfo.xml"]
        assert "<PageCount>3</PageCount>" in archive.read("ComicInfo.xml").decode()
        with Image.open(io.BytesIO(archive.read("001.jpg"))) as image:
            assert image.size == (600, 800) and image.mode == "L"  # siv original ostaje siv
    listed = client.get(f"/api/projects/{project_id}/exports").json()
    assert listed[0]["status"] == "done" and listed[0]["size"] > 0


def test_pdf_has_one_page_per_image_at_300_dpi(client):
    project_id, _ = project_with_pages(client)

    export, job = export_album(client, project_id, format="pdf", skipped="omit")

    assert job["status"] == "done", job
    document = pdfium.PdfDocument(client.get(f"/api/exports/{export['id']}/file").content)
    assert len(document) == 2  # preskočena je izostavljena
    assert round(document[0].get_size()[0]) == round(600 * 72 / 300)


def test_page_with_wrong_size_or_outside_export_is_rejected(client):
    project_id, pages = project_with_pages(client)
    export = client.post(f"/api/projects/{project_id}/exports", json={}).json()

    wrong = client.put(
        f"/api/exports/{export['id']}/pages/1",
        content=png((300, 400)),
        headers={"content-type": "image/png"},
    )
    outside = client.put(
        f"/api/exports/{export['id']}/pages/99",
        content=png((600, 800)),
        headers={"content-type": "image/png"},
    )

    assert wrong.status_code == 400 and "600×800" in wrong.json()["detail"]
    assert outside.status_code == 400


def test_missing_rendered_page_fails_the_export(client):
    project_id, _ = project_with_pages(client)
    export = client.post(f"/api/projects/{project_id}/exports", json={}).json()

    job = client.post(f"/api/exports/{export['id']}/finish").json()
    run_worker(client)

    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "failed"
    assert client.get(f"/api/projects/{project_id}/exports").json()[0]["status"] == "failed"
    assert client.post(f"/api/exports/{export['id']}/finish").status_code == 409
    assert client.delete(f"/api/exports/{export['id']}").status_code == 204


def test_readiness_reports_uncleaned_and_untranslated_pages(client):
    project_id, pages = project_with_pages(client)
    block = {"x": 10, "y": 10, "width": 100, "height": 40, "text": "CIAO", "kind": "speech"}
    client.post(f"/api/pages/{pages[0]['id']}/blocks", json=block)

    check = client.get(f"/api/projects/{project_id}/export-check").json()

    assert check[0] == {
        "position": 1,
        "page_id": pages[0]["id"],
        "skip": False,
        "cleaned": False,
        "reviewed": False,
        "blocks": 1,
        "untranslated": 1,
    }
    assert check[1]["skip"] is True


def test_deleting_project_removes_its_exports(client):
    from pathlib import Path

    project_id, _ = project_with_pages(client)
    export, _ = export_album(client, project_id)
    folder = Path(client.app.state.settings.data_dir, "exports", str(export["id"]))
    assert folder.exists()

    assert client.delete(f"/api/projects/{project_id}").status_code == 204

    assert not folder.exists()


def test_drawing_progress_is_shown_in_the_job_list_and_project_progress(client, monkeypatch):
    """Crtanje albuma radi browser: server broji primljene stranice za Status i korak 8."""
    from app.services import exporting

    project_id, pages = project_with_pages(client)  # 3 stranice, druga je preskočena
    export = client.post(f"/api/projects/{project_id}/exports", json={}).json()

    drawing = [job for job in client.get("/api/jobs").json() if job["type"] == "export_draw"]
    assert [(job["id"], job["progress"], job["total"]) for job in drawing] == [
        (-export["id"], 0, 2)
    ]
    assert drawing[0]["project_title"]
    progress = client.get(f"/api/projects/{project_id}").json()["progress"]
    assert progress["export_active"] == {"stage": "drawing", "done": 0, "total": 2, "stale": False}

    client.put(
        f"/api/exports/{export['id']}/pages/1",
        content=png((600, 800)),
        headers={"content-type": "image/png"},
    )
    drawing = [job for job in client.get("/api/jobs").json() if job["type"] == "export_draw"]
    assert (drawing[0]["progress"], drawing[0]["result"]) == (1, None)

    # tab sa izvozom je zatvoren: posle pauze crtanje „čeka", a posle sat vremena se ne prikazuje
    monkeypatch.setattr(exporting, "STALE_SECONDS", -1)
    drawing = [job for job in client.get("/api/jobs").json() if job["type"] == "export_draw"]
    assert drawing[0]["result"] == {"stage": "čeka otvoren tab za izvoz"}
    monkeypatch.setattr(exporting, "ABANDONED_SECONDS", -1)
    assert [job for job in client.get("/api/jobs").json() if job["type"] == "export_draw"] == []

    monkeypatch.setattr(exporting, "ABANDONED_SECONDS", 3600)
    client.put(
        f"/api/exports/{export['id']}/pages/3",
        content=png((600, 800)),
        headers={"content-type": "image/png"},
    )
    client.post(f"/api/exports/{export['id']}/finish")
    progress = client.get(f"/api/projects/{project_id}").json()["progress"]
    assert progress["export_active"]["stage"] == "packing"
    run_worker(client)
    assert client.get(f"/api/projects/{project_id}").json()["progress"]["export_active"] is None
