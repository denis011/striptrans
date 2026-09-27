import base64
import io
import json

import httpx
import numpy as np
from factories import create_page
from PIL import Image

from app.services import ai_patch, llm
from app.services.openrouter import OpenRouterClient
from worker.main import run_once


def image_reply(size=(300, 120)) -> dict:
    """Odgovor modela za slike: PNG druge veličine nego isečak (model vraća svoju razmeru)."""
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, "PNG")
    url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    return {
        "choices": [{"message": {"images": [{"image_url": {"url": url}}]}}],
        "usage": {"cost": 0.034},
    }


def fake_remote(requests: list):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=image_reply())

    return OpenRouterClient(
        "https://openrouter.ai/api/v1", "tajna", transport=httpx.MockTransport(handler)
    )


def title_block(client, page, kind="title"):
    body = {"x": 100, "y": 100, "width": 200, "height": 80, "text": "SWACK", "kind": kind}
    block = client.post(f"/api/pages/{page['id']}/blocks", json=body).json()
    client.patch(f"/api/blocks/{block['id']}", json={"translation": "SCVAK"})
    return block


def test_ai_patch_is_only_for_titles_signs_and_sound_effects(client):
    client.app.state.settings.openrouter_api_key = "tajna"
    page = create_page(client)
    speech = title_block(client, page, kind="speech")

    response = client.post(f"/api/blocks/{speech['id']}/ai-patch", json={})

    assert response.status_code == 400


def test_proposal_is_fitted_to_the_crop_and_accepted_as_a_patch_over_the_block(client, monkeypatch):
    state = client.app.state
    state.settings.openrouter_api_key = "tajna"
    requests: list = []
    monkeypatch.setattr(llm, "remote_client", lambda settings=None: fake_remote(requests))
    page = create_page(client)
    block = title_block(client, page)

    job = client.post(f"/api/blocks/{block['id']}/ai-patch", json={"quality": "cheap"}).json()
    run_once(state.session_factory, "w1", state.settings)

    done = client.get(f"/api/jobs/{job['id']}").json()
    assert done["status"] == "done", done["error"]
    assert done["result"]["cost"] == 0.034
    assert done["result"]["model"] == state.settings.ai_image_cheap_model
    sent = requests[0]
    assert sent["model"] == "google/gemini-3.1-flash-lite-image"
    assert '"SWACK"' in sent["messages"][0]["content"][0]["text"]
    assert '"SCVAK"' in sent["messages"][0]["content"][0]["text"]
    # predlog ima tačno veličinu isečka (blok + 12 % margine), a strana je crno-bela: siva slika
    x, y, width, height = done["result"]["box"]
    proposal = Image.open(io.BytesIO(client.get(f"/api/jobs/{job['id']}/ai-image").content))
    assert proposal.size == (width, height) and proposal.mode == "L"

    proposals = client.get(f"/api/blocks/{block['id']}/ai-proposals").json()
    assert [item["job_id"] for item in proposals] == [job["id"]]
    patch = client.post(f"/api/jobs/{job['id']}/ai-accept").json()
    # ceo predlog se razlikuje od originala: zakrpa pokriva blok i pojas oko njega, ne ceo isečak
    assert patch["x"] <= 100 and patch["y"] <= 100
    assert patch["x"] + patch["width"] >= 300 and patch["y"] + patch["height"] >= 180
    assert patch["x"] >= x and patch["x"] + patch["width"] <= x + width
    assert patch["above_text"] is True
    assert client.post(f"/api/pages/{page['id']}/undo").json()["action"] == "AI prepravka"
    assert client.get(f"/api/pages/{page['id']}/patches").json() == []
    # isti (plaćen) predlog se prihvata ponovo bez novog poziva modela
    assert client.post(f"/api/jobs/{job['id']}/ai-accept").status_code == 201
    assert len(requests) == 1


def test_patch_keeps_letters_that_leave_the_block_but_not_far_changes():
    """SWACK → SCVAK: slova koja izlaze iz okvira ulaze u zakrpu, a izmena crteža u uglu ne."""
    original = np.full((100, 300), 255, np.uint8)
    proposal = original.copy()
    proposal[40:60, 60:240] = 0  # nova slova: blok je 100–200, slova idu od 60 do 240
    proposal[0:8, 0:8] = 0  # model je usput izmenio crtež u uglu isečka
    block = (100, 30, 100, 40)

    mask = ai_patch.change_mask(original, proposal, block)

    assert mask[50, 60] and mask[50, 239]  # slova van okvira su tu
    assert mask[35, 150]  # ceo okvir bloka (stara slova nestaju)
    assert not mask[3, 3]  # dalja izmena crteža nije

    piece, (x, y, width, height) = ai_patch.masked(Image.fromarray(proposal), mask)
    alpha = np.asarray(piece)[..., 3]
    assert x <= 60 and x + width >= 240 and y > 8
    assert alpha[50 - y, 150 - x] == 255


def test_project_progress_sums_the_cost_of_ai_proposals(client, monkeypatch):
    state = client.app.state
    state.settings.openrouter_api_key = "tajna"
    monkeypatch.setattr(llm, "remote_client", lambda settings=None: fake_remote([]))
    page = create_page(client)
    block = title_block(client, page)
    for _ in range(2):  # „Pokušaj ponovo": svaki predlog se plaća
        client.post(f"/api/blocks/{block['id']}/ai-patch", json={})
        run_once(state.session_factory, "w1", state.settings)

    project_id = client.get("/api/projects").json()[0]["id"]
    progress = client.get(f"/api/projects/{project_id}").json()["progress"]
    assert (progress["ai_calls"], progress["ai_cost"]) == (2, 0.068)
