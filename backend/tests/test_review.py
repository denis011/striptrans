from factories import create_page

from app.services.spellcheck import allowed_words, unknown_words


def add_block(client, page, text, translation, kind="speech", y=10):
    body = {"x": 10, "y": y, "width": 200, "height": 60, "text": text, "kind": kind}
    block = client.post(f"/api/pages/{page['id']}/blocks", json=body).json()
    if translation:
        client.patch(f"/api/blocks/{block['id']}", json={"translation": translation})
    return block


def review(client, page):
    return client.get(f"/api/pages/{page['id']}/review").json()


def test_unknown_words_ignores_case_and_allowed_words():
    assert unknown_words("ŠERIF JE STIGAO") == []
    assert unknown_words("STIGAO JE DAULER") == ["DAULER"]
    assert unknown_words("STIGAO JE DAULER", allowed_words("RUFUS DAULER")) == []
    assert unknown_words("BRLJ BRLJ") == ["BRLJ"]  # ista reč se prijavljuje jednom


def test_page_review_reports_spelling_glossary_and_length(client):
    page = create_page(client)
    client.post("/api/series/1/glossary", json={"source": "MICO", "target": "MIĆO", "kind": "name"})
    add_block(client, page, "MICO, ANDIAMO!", "BRZO, IDEMO!")  # glosar nije upotrebljen
    add_block(client, page, "E' LUI!", "TO JE ON, BAŠ ON, ZAISTA ON!", y=100)  # predugačko
    add_block(client, page, "SWACK", "SCVAK", kind="sfx", y=200)  # onomatopeja se ne proverava
    add_block(client, page, "GREYWOOD!", "GREJVUD!", y=300)

    body = review(client, page)

    assert body["reviewed"] is False
    first, second, third, fourth = body["blocks"]
    assert first["glossary_missing"] == ["MIĆO"] and first["unknown"] == []
    assert second["too_long"] is True
    assert third["unknown"] == [] and third["glossary_missing"] == []
    assert fourth["unknown"] == ["GREJVUD"]


def test_word_added_to_dictionary_stops_being_reported(client):
    page = create_page(client)
    add_block(client, page, "GREYWOOD!", "GREJVUD!")
    assert review(client, page)["blocks"][0]["unknown"] == ["GREJVUD"]

    created = client.post("/api/series/1/dictionary", json={"word": "Grejvud"})

    assert created.status_code == 201 and created.json()["word"] == "grejvud"
    assert review(client, page)["blocks"][0]["unknown"] == []
    assert [w["word"] for w in client.get("/api/series/1/dictionary").json()] == ["grejvud"]


def test_dictionary_word_is_added_once_and_can_be_removed(client):
    first = client.post("/api/series/1/dictionary", json={"word": "mićo"}).json()
    again = client.post("/api/series/1/dictionary", json={"word": " MIĆO "})

    assert again.status_code == 201 and again.json()["id"] == first["id"]
    assert client.delete(f"/api/dictionary/{first['id']}").status_code == 204
    assert client.get("/api/series/1/dictionary").json() == []
    assert client.delete(f"/api/dictionary/{first['id']}").status_code == 404


def test_glossary_term_counts_with_case_endings(client):
    page = create_page(client)
    client.post(
        "/api/series/1/glossary", json={"source": "NORAH", "target": "NORA", "kind": "name"}
    )
    add_block(client, page, "NORAH!", "NORU SAM VIDEO!")

    assert review(client, page)["blocks"][0]["glossary_missing"] == []


def test_croatian_and_ijekavian_words_are_reported(client):
    """Rečnik prihvata TISUĆU i UVIJEK, pa lektura posebno javlja reči koje nisu srpske."""
    page = create_page(client)
    add_block(client, page, "PER MILLE SCALPI!", "TISUĆU MI SKALPOVA!")
    add_block(client, page, "CHI E'? E' SEMPRE QUI!", "TKO JE TO? UVIJEK JE OVDJE!", y=100)
    add_block(client, page, "PER MILLE SCALPI!", "HILJADU MU SKALPOVA!", y=200)

    first, second, third = review(client, page)["blocks"]

    assert first["non_serbian"] == ["TISUĆU"]
    assert second["non_serbian"] == ["TKO", "UVIJEK", "OVDJE"] and second["unknown"] == []
    assert third["non_serbian"] == []


def test_emphasis_not_carried_over_is_reported(client):
    page = create_page(client)
    add_block(client, page, "*FERMO!*... LASCIA\nCHE SIA IO!", "STANI!... PUSTI MENE!")
    add_block(client, page, "*FERMO!*... LASCIA\nCHE SIA IO!", "*STANI!*... PUSTI MENE!", y=100)
    add_block(client, page, "LASCIA CHE SIA IO!", "PUSTI MENE!", y=200)

    body = review(client, page)

    assert [b["emphasis_missing"] for b in body["blocks"]] == [True, False, False]
    assert body["blocks"][1]["unknown"] == []  # zvezdice nisu deo reči
