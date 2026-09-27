from pathlib import Path

import httpx
import pytest
from factories import create_page, jpeg_bytes, zip_bytes
from llama_mock import llama_client, refused, reply

from app.jobs import recover_interrupted_jobs
from app.models import Job
from app.services import page_processing
from app.services.detector import Detection
from worker.main import run_once

DETECTIONS = [
    Detection("text_bubble", 0.9, (400, 100, 100, 50)),  # desno
    Detection("text_bubble", 0.9, (50, 120, 100, 50)),  # levo i malo niže: isti red, čita se prvo
    Detection("bubble", 0.9, (30, 100, 150, 100)),
    Detection("text_free", 0.8, (50, 600, 200, 40)),
]


SFX = []


@pytest.fixture(autouse=True)
def fake_detector(monkeypatch):
    monkeypatch.setattr(page_processing, "detect", lambda image, path: DETECTIONS)
    monkeypatch.setattr(page_processing, "sfx_candidates", lambda image, known, path: SFX)


def ocr_client(texts):
    answers = iter(texts)

    def handler(request: httpx.Request) -> httpx.Response:
        answer = next(answers)
        if answer is None:  # model nije uspeo na ovom bloku
            return httpx.Response(500, json={"error": {"message": "failed to decode"}})
        return reply(answer)

    return llama_client(handler)


def run_worker(client, llama=None) -> bool:
    state = client.app.state
    return run_once(state.session_factory, "w1", state.settings, llama)


def project_with_pages(client, count):
    project = client.post("/api/projects", json={"series_id": 1}).json()
    archive = zip_bytes([(f"{i}.jpg", jpeg_bytes(size=(600, 800))) for i in range(1, count + 1)])
    client.post(
        f"/api/projects/{project['id']}/imports",
        data={"kind": "original"},
        files=[("files", ("a.cbz", archive, "application/zip"))],
    )
    run_worker(client)
    return project, client.get(f"/api/projects/{project['id']}/pages").json()


def add_block(client, page):
    body = {"x": 1, "y": 1, "width": 10, "height": 10}
    client.post(f"/api/pages/{page['id']}/blocks", json=body)


def test_process_page_replaces_blocks_in_reading_order(client):
    page = create_page(client)
    add_block(client, page)

    job = client.post(f"/api/pages/{page['id']}/process", json={"model": "qwen2.5vl:7b"}).json()
    assert run_worker(client, ocr_client(["LEVO", "DESNO", "DOLE"])) is True

    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "done", job["error"]
    assert job["result"] == {"blocks": 3, "needs_review": 0, "skipped": False}
    assert (job["progress"], job["total"]) == (3, 3)
    blocks = client.get(f"/api/pages/{page['id']}/blocks").json()
    assert [(b["text"], b["kind"], b["source"], b["ocr_model"]) for b in blocks] == [
        ("LEVO", "speech", "auto", "qwen2.5vl:7b"),
        ("DESNO", "speech", "auto", "qwen2.5vl:7b"),
        ("DOLE", "caption", "auto", "qwen2.5vl:7b"),
    ]
    assert blocks[0]["bubble_polygon"] == [[30, 100], [180, 100], [180, 200], [30, 200]]
    assert blocks[1]["bubble_polygon"] is None


def test_block_where_the_model_fails_is_left_for_review(client):
    _, pages = project_with_pages(client, 1)
    job = client.post(f"/api/pages/{pages[0]['id']}/process").json()

    run_worker(client, ocr_client(["LEVO", None, "DOLE"]))

    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"
    blocks = client.get(f"/api/pages/{pages[0]['id']}/blocks").json()
    assert [(b["text"], b["needs_review"]) for b in blocks] == [
        ("LEVO", False),
        ("", True),
        ("DOLE", False),
    ]


def test_block_deleted_while_ocr_runs_is_skipped(client):
    """Obrada traje, a korisnik u editoru obriše blok (ili poništi): posao ne sme da padne."""
    from sqlalchemy import select

    from app.models import TextBlock

    page = create_page(client)
    job = client.post(f"/api/pages/{page['id']}/process").json()
    state = client.app.state
    answers = iter(["LEVO", "DESNO"])

    def handler(request: httpx.Request) -> httpx.Response:
        answer = next(answers)
        if answer == "DESNO":  # dok se čita drugi blok, treći nestaje
            with state.session_factory() as session:
                query = select(TextBlock).where(TextBlock.page_id == page["id"])
                third = session.scalars(query.order_by(TextBlock.position)).all()[2]
                session.delete(third)
                session.commit()
        return reply(answer)

    run_worker(client, llama_client(handler))

    finished = client.get(f"/api/jobs/{job['id']}").json()
    assert finished["status"] == "done", finished["error"]
    blocks = client.get(f"/api/pages/{page['id']}/blocks").json()
    assert [b["text"] for b in blocks] == ["LEVO", "DESNO"]


def test_process_project_skips_marked_pages_and_pages_with_blocks(client):
    project, pages = project_with_pages(client, 3)
    client.patch(f"/api/pages/{pages[1]['id']}", json={"skip": True})
    add_block(client, pages[2])

    job = client.post(f"/api/projects/{project['id']}/process", json={}).json()
    run_worker(client, ocr_client(["A", "B", "C"]))

    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "done", job["error"]
    assert job["result"] == {"pages": 1, "blocks": 3, "needs_review": 0, "skipped": 2}
    assert (job["progress"], job["total"]) == (3, 3)
    assert len(client.get(f"/api/pages/{pages[2]['id']}/blocks").json()) == 1


def test_interrupted_ocr_is_finished_when_the_project_is_processed_again(client):
    """Detekcija je upisala blokove, a OCR je prekinut: nastavak čita samo nepročitane blokove."""
    from app.models import TextBlock

    project, pages = project_with_pages(client, 1)
    client.post(f"/api/pages/{pages[0]['id']}/process").json()
    run_worker(client, ocr_client(["LEVO", "DESNO", "DOLE"]))
    blocks = client.get(f"/api/pages/{pages[0]['id']}/blocks").json()
    client.patch(f"/api/blocks/{blocks[0]['id']}", json={"text": "LEVO ISPRAVLJENO"})
    state = client.app.state
    with state.session_factory() as session:
        for block in blocks[1:]:
            unread = session.get(TextBlock, block["id"])
            unread.text, unread.ocr_text, unread.ocr_model = "", "", None
        session.commit()

    progress = client.get(f"/api/projects/{project['id']}").json()["progress"]
    assert (progress["with_blocks"], progress["unread"]) == (0, 2)

    job = client.post(f"/api/projects/{project['id']}/process", json={}).json()
    run_worker(client, ocr_client(["B", "C"]))

    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "done", job["error"]
    assert job["result"] == {"pages": 1, "blocks": 2, "needs_review": 0, "skipped": 0}
    blocks = client.get(f"/api/pages/{pages[0]['id']}/blocks").json()
    assert [b["text"] for b in blocks] == ["LEVO ISPRAVLJENO", "B", "C"]
    progress = client.get(f"/api/projects/{project['id']}").json()["progress"]
    assert (progress["with_blocks"], progress["unread"]) == (1, 0)


def test_cancelling_queued_job_prevents_it_from_running(client):
    page = create_page(client)
    job = client.post(f"/api/pages/{page['id']}/process").json()

    assert client.post(f"/api/jobs/{job['id']}/cancel").json()["status"] == "cancelled"
    assert run_worker(client, ocr_client([])) is False


def test_running_job_stops_when_cancel_is_requested(client):
    project, _ = project_with_pages(client, 2)
    job = client.post(f"/api/projects/{project['id']}/process").json()
    with client.app.state.session_factory() as session:
        session.get(Job, job["id"]).cancel_requested = True
        session.commit()

    run_worker(client, ocr_client(["A"] * 6))

    job = client.get(f"/api/jobs/{job['id']}").json()
    assert (job["status"], job["progress"]) == ("cancelled", 0)


def test_sfx_candidates_become_sfx_blocks_marked_for_review(client, monkeypatch):
    monkeypatch.setattr(
        page_processing, "sfx_candidates", lambda image, known, path: [(300, 400, 150, 100)]
    )
    page = create_page(client)

    job = client.post(f"/api/pages/{page['id']}/process", json={"model": "qwen2.5vl:7b"}).json()
    run_worker(client, ocr_client(["LEVO", "DESNO", "SWACK", "DOLE"]))

    assert client.get(f"/api/jobs/{job['id']}").json()["result"]["needs_review"] == 1

    blocks = client.get(f"/api/pages/{page['id']}/blocks").json()
    sfx = [b for b in blocks if b["kind"] == "sfx"]
    assert [(b["text"], b["needs_review"], b["x"]) for b in sfx] == [("SWACK", True, 300)]
    assert all(not b["needs_review"] for b in blocks if b["kind"] != "sfx")


def test_interrupted_processing_is_requeued_unless_it_replaces_blocks(client):
    page = create_page(client)
    resumable = client.post(f"/api/pages/{page['id']}/process").json()
    with client.app.state.session_factory() as session:
        job = session.get(Job, resumable["id"])
        job.status, job.progress = "running", 3
        other = Job(
            type="process_project", status="running", payload={"project_id": 1, "replace": True}
        )
        session.add(other)
        session.commit()

        assert recover_interrupted_jobs(session, Path(client.app.state.settings.data_dir)) == 2
        assert (job.status, job.progress) == ("queued", 0)
        assert other.status == "failed"


def test_active_jobs_are_listed_in_queue_order_with_project_title(client):
    project, pages = project_with_pages(client, 1)
    client.patch(f"/api/projects/{project['id']}", json={"issue_number": "682"})
    first = client.post(f"/api/pages/{pages[0]['id']}/process").json()
    second = client.post(f"/api/projects/{project['id']}/process", json={}).json()

    jobs = client.get("/api/jobs").json()

    assert [job["id"] for job in jobs] == [first["id"], second["id"]]
    assert all(job["status"] == "queued" for job in jobs)
    assert "682" in jobs[0]["project_title"]
    run_worker(client, ocr_client(["A", "B", "C"]))  # worker uzima jedan posao po pozivu
    run_worker(client, ocr_client([]))
    assert client.get("/api/jobs").json() == []  # gotovi poslovi se ne prikazuju


def test_job_waits_in_the_queue_while_llama_server_is_down(client):
    """llama-server je ugašen ili učitava model: posao se vraća u red i nastavlja kad proradi."""
    project, pages = project_with_pages(client, 1)
    client.app.state.settings.worker_retry_interval = 0
    job = client.post(f"/api/projects/{project['id']}/process", json={}).json()

    down = llama_client(refused)
    assert run_worker(client, down) is False  # nije obrađen, čeka

    waiting = client.get(f"/api/jobs/{job['id']}").json()
    assert (waiting["status"], waiting["error"]) == ("queued", None)
    assert run_worker(client, ocr_client(["A", "B", "C"])) is True
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"
