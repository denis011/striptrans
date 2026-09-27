import numpy as np
from factories import create_page
from test_page_translation import llm

from app.services import cleaning
from worker.main import run_once


def fake_mask(image):
    width, height = image.size
    return np.zeros((height, width), dtype=np.float32)


def test_prepare_translates_and_cleans_and_skips_what_is_done(client, monkeypatch):
    monkeypatch.setattr(cleaning, "text_mask", lambda image, path: fake_mask(image))
    page = create_page(client)
    project_id = client.get("/api/projects").json()[0]["id"]
    body = {"x": 100, "y": 100, "width": 200, "height": 60, "text": "CIAO!", "kind": "speech"}
    client.post(f"/api/pages/{page['id']}/blocks", json=body)
    state = client.app.state

    job = client.post(f"/api/projects/{project_id}/prepare", json={}).json()
    requests: list = []
    llm(monkeypatch, [[{"number": 1, "text": "ZDRAVO!"}]], requests)
    run_once(state.session_factory, "w1", state.settings)

    finished = client.get(f"/api/jobs/{job['id']}").json()
    assert finished["status"] == "done", finished
    assert finished["result"] == {
        "ocr_pages": 0,  # stranica već ima blokove
        "blocks": 0,
        "translated": 1,
        "from_memory": 0,
        "cleaned": 1,
    }
    assert client.get(f"/api/pages/{page['id']}/blocks").json()[0]["translation"] == "ZDRAVO!"

    again = client.post(f"/api/projects/{project_id}/prepare", json={}).json()
    llm(monkeypatch, [], requests)
    run_once(state.session_factory, "w1", state.settings)
    result = client.get(f"/api/jobs/{again['id']}").json()["result"]
    assert (result["translated"], result["cleaned"]) == (0, 0)  # ništa novo: sve preskočeno
