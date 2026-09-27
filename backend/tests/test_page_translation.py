from factories import create_page, jpeg_bytes, zip_bytes
from remote_mock import use_remote

from app.models import TranslationMemory
from worker.main import run_once


def llm(monkeypatch, answers: list, requests: list) -> None:
    use_remote(monkeypatch, [{"translations": answer} for answer in answers], requests)


def add_block(client, page, text, y=10, **fields):
    body = {"x": 10, "y": y, "width": 200, "height": 60, "text": text}
    block = client.post(f"/api/pages/{page['id']}/blocks", json=body).json()
    if fields:
        block = client.patch(f"/api/blocks/{block['id']}", json=fields).json()
    return block


def blocks(client, page):
    return client.get(f"/api/pages/{page['id']}/blocks").json()


def run_worker(client):
    state = client.app.state
    return run_once(state.session_factory, "w1", state.settings)


def remember(client, series_id, source, target):
    with client.app.state.session_factory() as session:
        session.add(TranslationMemory(series_id=series_id, source=source, target=target))
        session.commit()


def test_translate_page_uses_memory_glossary_and_keeps_edited(client, monkeypatch):
    page = create_page(client)
    add_block(client, page, "MICO, ANDIA-\nMO!")
    add_block(client, page, "AIUTO!", y=100)
    add_block(client, page, "E' LUI!", y=200, translation="to je on!")
    client.post("/api/series/1/glossary", json={"source": "MICO", "target": "MIĆO", "kind": "name"})
    remember(client, 1, "AIUTO!", "U POMOĆ!")
    requests = []

    job = client.post(f"/api/pages/{page['id']}/translate", json={"model": "or:test/model"}).json()
    llm(monkeypatch, [[{"number": 1, "text": "mićo, idemo!"}]], requests)
    run_worker(client)

    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "done", job["error"]
    assert job["result"] == {"translated": 1, "from_memory": 1, "too_long": 0}
    assert [
        (b["translation"], b["translation_status"], b["translation_model"])
        for b in blocks(client, page)
    ] == [
        ("MIĆO, IDEMO!", "draft", "or:test/model"),
        ("U POMOĆ!", "draft", "memorija"),
        ("TO JE ON!", "edited", None),
    ]
    prompt = requests[0]["prompt"]
    assert "1. [speech] MICO, ANDIAMO!" in prompt and "E' LUI" not in prompt
    assert "- MICO → MIĆO" in prompt and "- AIUTO! → U POMOĆ!" in prompt


def test_too_long_translation_is_shortened(client, monkeypatch):
    page = create_page(client)
    add_block(client, page, "E' LUI!")
    requests = []
    answers = [
        [{"number": 1, "text": "TO JE ON, BAŠ ON, ZAISTA!"}],
        [{"number": 1, "text": "TO JE ON!"}],
    ]

    client.post(f"/api/pages/{page['id']}/translate")
    llm(monkeypatch, answers, requests)
    run_worker(client)

    [block] = blocks(client, page)
    assert (block["translation"], block["translation_too_long"]) == ("TO JE ON!", False)
    assert len(requests) == 2


def test_translate_project_skips_translated_blocks_and_skipped_pages(client, monkeypatch):
    project = client.post("/api/projects", json={"series_id": 1}).json()
    archive = zip_bytes([(f"{i}.jpg", jpeg_bytes(size=(600, 800))) for i in (1, 2)])
    client.post(
        f"/api/projects/{project['id']}/imports",
        data={"kind": "original"},
        files=[("files", ("a.cbz", archive, "application/zip"))],
    )
    run_worker(client)
    first, second = client.get(f"/api/projects/{project['id']}/pages").json()
    done = add_block(client, first, "AH!")
    client.patch(f"/api/blocks/{done['id']}", json={"translation_status": "draft"})
    add_block(client, first, "CIAO!", y=100)
    add_block(client, second, "NON TRADURRE", y=100)
    client.patch(f"/api/pages/{second['id']}", json={"skip": True})
    requests = []

    job = client.post(
        f"/api/projects/{project['id']}/translate", json={"model": "or:test/model"}
    ).json()
    llm(monkeypatch, [[{"number": 1, "text": "ZDRAVO!"}]], requests)
    run_worker(client)

    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["result"] == {"pages": 1, "translated": 1, "from_memory": 0, "too_long": 0}
    assert (
        len(requests) == 1
        and "CIAO!" in requests[0]["prompt"]
        and "[speech] AH!" not in requests[0]["prompt"]
    )


def test_single_block_translate_and_shorter(client, monkeypatch):
    requests = []
    answers = [[{"number": 1, "text": "TO JE ON, BAŠ ON!"}], [{"number": 1, "text": "TO JE ON!"}]]
    llm(monkeypatch, answers, requests)
    page = create_page(client)
    block = add_block(client, page, "E' LUI!")

    translated = client.post(
        f"/api/blocks/{block['id']}/translate", json={"model": "or:test/model"}
    ).json()
    shorter = client.post(
        f"/api/blocks/{block['id']}/translate", json={"model": "or:test/model", "shorter": True}
    ).json()

    assert (translated["translation"], translated["translation_too_long"]) == (
        "TO JE ON, BAŠ ON!",
        True,
    )
    assert (shorter["translation"], shorter["translation_status"]) == ("TO JE ON!", "draft")
    assert "too long for the balloon: TO JE ON, BAŠ ON!" in requests[1]["prompt"]


def test_edit_and_approve_translation_remembers_it(client):
    page = create_page(client)
    block = add_block(client, page, "CIAO!")

    edited = client.patch(f"/api/blocks/{block['id']}", json={"translation": "zdravo!"}).json()
    approved = client.patch(
        f"/api/blocks/{block['id']}", json={"translation_status": "approved"}
    ).json()

    assert (edited["translation"], edited["translation_status"]) == ("ZDRAVO!", "edited")
    assert approved["translation_status"] == "approved"
    with client.app.state.session_factory() as session:
        [entry] = session.query(TranslationMemory).all()
        assert (entry.source, entry.target) == ("CIAO!", "ZDRAVO!")


def test_translation_models_come_from_openrouter(client):
    assert client.get("/api/translation/models").status_code == 502  # bez ključa nema prevoda

    client.app.state.settings.openrouter_api_key = "tajna"
    client.app.state.settings.openrouter_models = "or:test/model,or:drugi/model"
    body = client.get("/api/translation/models").json()

    assert body["default_model"] == "or:test/model"
    assert [model["name"] for model in body["models"]] == ["or:test/model", "or:drugi/model"]


def test_local_model_name_is_rejected(client):
    page = create_page(client)
    block = add_block(client, page, "CIAO!")

    response = client.post(f"/api/blocks/{block['id']}/translate", json={"model": "gemma3:12b"})

    assert response.status_code == 502
    assert "OpenRouter" in response.json()["detail"]
