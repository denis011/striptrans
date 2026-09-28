from factories import create_page
from remote_mock import use_remote
from test_page_translation import add_block, blocks, run_worker

from app.services.translation import DEFAULT_STYLE


def answer(text, note=""):
    return {"translations": [{"number": 1, "text": text, "note": note}]}


def styles(client):
    return client.get("/api/translation-styles").json()


def test_builtin_style_is_active_and_resets(client):
    [builtin] = styles(client)
    assert (builtin["name"], builtin["builtin"], builtin["active"]) == ("Podrazumevani", True, True)
    assert builtin["text"] == DEFAULT_STYLE and builtin["changed"] is False

    changed = client.patch(
        f"/api/translation-styles/{builtin['id']}", json={"text": "- KRATKO."}
    ).json()
    assert (changed["text"], changed["changed"]) == ("- KRATKO.", True)
    reset = client.post(f"/api/translation-styles/{builtin['id']}/reset").json()
    assert (reset["text"], reset["changed"]) == (DEFAULT_STYLE, False)
    assert client.delete(f"/api/translation-styles/{builtin['id']}").status_code == 400


def test_saved_styles_one_active(client):
    [builtin] = styles(client)
    modern = client.post("/api/translation-styles", json={"name": "Moderni", "text": "- SLENG."})
    assert modern.status_code == 201
    modern = modern.json()
    duplicate = client.post("/api/translation-styles", json={"name": "Moderni", "text": "x"})
    assert duplicate.status_code == 409
    assert client.post(f"/api/translation-styles/{modern['id']}/reset").status_code == 400

    client.post(f"/api/translation-styles/{modern['id']}/activate")
    assert [s["active"] for s in styles(client)] == [False, True]
    client.delete(f"/api/translation-styles/{modern['id']}")  # aktivan stil se briše
    assert [(s["id"], s["active"]) for s in styles(client)] == [(builtin["id"], True)]


def test_prompt_has_active_style_and_series_notes_and_note_is_kept_apart(client, monkeypatch):
    page = create_page(client)
    add_block(client, page, "PER MILLE BALENE!")
    modern = client.post("/api/translation-styles", json={"name": "Moderni", "text": "- SLENG."})
    client.post(f"/api/translation-styles/{modern.json()['id']}/activate")
    series = client.patch("/api/series/1", json={"translation_notes": "  Glavni lik je odmeren.  "})
    assert series.json()["translation_notes"] == "Glavni lik je odmeren."
    requests = []
    use_remote(monkeypatch, [answer("HILJADU KITOVA!", "igra reči sa kitovima")], requests)

    client.post(f"/api/pages/{page['id']}/translate", json={"model": "or:test/model"})
    run_worker(client)

    prompt = requests[0]["prompt"]
    assert "Translation style:\n- SLENG." in prompt
    assert "Notes for this comic series:\nGlavni lik je odmeren." in prompt
    assert DEFAULT_STYLE not in prompt
    [block] = blocks(client, page)
    assert (block["translation"], block["translation_note"]) == (
        "HILJADU KITOVA!",
        "igra reči sa kitovima",
    )


def test_preview_does_not_save_and_uses_chosen_style(client, monkeypatch):
    page = create_page(client)
    block = add_block(client, page, "ANDIAMO!", translation="IDEMO!")
    other = client.post("/api/translation-styles", json={"name": "Probni", "text": "- PROBA."})
    requests = []
    use_remote(monkeypatch, [answer("HAJDEMO!", "")], requests)

    body = {"model": "or:test/model", "style_id": other.json()["id"]}
    preview = client.post(f"/api/blocks/{block['id']}/translate/preview", json=body)

    assert preview.json() == {"translation": "HAJDEMO!", "note": None}
    assert "Translation style:\n- PROBA." in requests[0]["prompt"]
    assert blocks(client, page)[0]["translation"] == "IDEMO!"
    missing = client.post(f"/api/blocks/{block['id']}/translate/preview", json={"style_id": 999})
    assert missing.status_code == 404
