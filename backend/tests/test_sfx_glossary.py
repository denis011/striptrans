from factories import create_page
from remote_mock import use_remote
from test_page_translation import add_block, blocks, run_worker

from app.services.sfx_glossary import adapt, key, proposals, translate

GLOSSARY = {
    "SWACK": "SCVAK",
    "WOAH": "VOAH!",
    "AH AH AH": "HA-HA-HA!",
    "BANG": "BANG",
    "CRASH": "KRAŠ",
}


def test_rule_adapts_only_words_with_sh_or_w():
    assert adapt("CRASH") == "KRAŠ"
    assert adapt("SWISH") == "SVIŠ"
    assert adapt("WHOOSH") == "VOOŠ"
    assert adapt("SWACK") == "SVAK"
    assert adapt("WOOOOSHHH") == "VOOOOŠŠŠ"
    assert adapt("SHREEE") == "ŠREEE"
    for word in ("BANG", "ZING", "FLAP", "SKREEK", "CLICK", "COUGH"):
        assert adapt(word) == word


def test_glossary_first_then_rule_per_word():
    assert key("  woah!! ") == "WOAH"
    assert translate("SWACK!", GLOSSARY) == "SCVAK!"
    assert translate("AH! AH! AH!", GLOSSARY) == "HA-HA-HA!"
    assert translate("WOAH...", GLOSSARY) == "VOAH..."  # znaci iz originala, ne iz glosara
    assert translate("BANG! SWISH! CLICK", GLOSSARY) == "BANG! SVIŠ! CLICK"


def test_seed_from_user_list(client):
    entries = {e["source"]: e["target"] for e in client.get("/api/sfx-glossary").json()}
    assert entries["SWACK"] == "SCVAK"
    assert entries["CRASH"] == "KRAŠ"
    assert entries["BANG"] == "BANG"


def test_crud_normalizes_source_and_rejects_duplicates(client):
    created = client.post("/api/sfx-glossary", json={"source": "zot!", "target": "zot"})
    assert created.status_code == 201
    assert created.json()["source"] == "ZOT"
    duplicate = client.post("/api/sfx-glossary", json={"source": "ZOT", "target": "X"})
    assert duplicate.status_code == 409
    entry_id = created.json()["id"]
    patched = client.patch(f"/api/sfx-glossary/{entry_id}", json={"target": "ZOTT"}).json()
    assert patched["target"] == "ZOTT"
    assert client.delete(f"/api/sfx-glossary/{entry_id}").status_code == 204
    assert client.post("/api/sfx-glossary", json={"source": "!!", "target": "X"}).status_code == 422


def test_missing_lists_words_not_in_glossary(client):
    page = create_page(client)
    add_block(client, page, "SPLASH! BANG!", kind="sfx")
    add_block(client, page, "SPLASH!", y=100, kind="sfx")
    add_block(client, page, "SPLASH!", y=200)  # nije onomatopeja
    serbian = client.post("/api/series", json={"name": "Srpsko", "source_lang": "sr"}).json()
    reference = create_page(client, series_id=serbian["id"])
    add_block(client, reference, "PLJAS!", kind="sfx")  # objavljeno izdanje se ne prevodi
    missing = client.get("/api/sfx-glossary/missing").json()
    assert missing == [{"source": "SPLASH", "suggestion": "SPLAŠ", "count": 2}]


def test_translate_page_does_not_send_sound_effects_to_model(client, monkeypatch):
    page = create_page(client)
    add_block(client, page, "CRASH!", kind="sfx")
    add_block(client, page, "AIUTO!", y=100)
    requests = []
    use_remote(monkeypatch, [{"translations": [{"number": 1, "text": "U POMOĆ!"}]}], requests)
    client.post(f"/api/pages/{page['id']}/translate", json={"model": "or:test/model"})
    run_worker(client)
    sound, speech = blocks(client, page)
    assert sound["translation"] == "KRAŠ!"
    assert speech["translation"] == "U POMOĆ!"
    assert "CRASH" not in str(requests)


def test_apply_to_project_keeps_edited(client):
    page = create_page(client)
    add_block(client, page, "SWISH!", kind="sfx", translation="SVUŠ!", translation_status="draft")
    add_block(client, page, "SWACK!", y=100, kind="sfx", translation="ŠVAK!")
    add_block(client, page, "SWISH!", y=200, kind="sfx")
    project_id = client.get("/api/projects").json()[0]["id"]
    result = client.post(f"/api/projects/{project_id}/sfx/apply").json()
    assert result == {"changed": 2}
    assert [b["translation"] for b in blocks(client, page)] == ["SVIŠ!", "ŠVAK!", "SVIŠ!"]
    assert client.post("/api/projects/999/sfx/apply").status_code == 404


def test_elongated_words_follow_the_glossary():
    assert translate("CRAAASH!", GLOSSARY) == "KRAAAŠ!"
    assert translate("CRASHHH", GLOSSARY) == "KRAŠŠŠ"
    assert translate("BAAANG! WOOOAH", GLOSSARY) == "BAAANG! VOOOAH"


def test_rule_and_elongated_words_wait_for_confirmation():
    assert proposals("SWISH! BANG! CRAAASH!", GLOSSARY) == [
        ("SWISH", "SVIŠ"),
        ("CRAAASH", "KRAAAŠ"),
    ]
    assert proposals("SWACK! ZING!", GLOSSARY) == []  # u glosaru ili se ne menja
    assert proposals("AH! AH! AH!", GLOSSARY) == []


def test_review_flags_unconfirmed_sound_until_added(client):
    page = create_page(client)
    sound = add_block(
        client, page, "SWISH!", kind="sfx", translation="SVIŠ!", translation_status="draft"
    )
    add_block(client, page, "SWOOSH!", y=100, kind="sfx", translation="VUŠ!")  # ručno: bez potvrde

    def flags():
        review = client.get(f"/api/pages/{page['id']}/review").json()["blocks"]
        return [b["sfx_unconfirmed"] for b in review]

    assert flags() == [[["SWISH", "SVIŠ"]], []]
    client.post("/api/sfx-glossary", json={"source": "SWISH", "target": "SVIŠ"})
    assert flags() == [[], []]
    assert sound["kind"] == "sfx"
