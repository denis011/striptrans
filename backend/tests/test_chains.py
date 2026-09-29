from factories import create_page
from remote_mock import use_remote
from test_page_translation import add_block, blocks, run_worker

from app.services.chains import join, split

COLUMN_1 = "IL VECCHIO FARO SI ACCENDE OGNI SERA E GUIDA LE BARCHE DEI PESCATORI DI"
COLUMN_2 = "LEVANTE FINO AL PORTO SICURO."


def test_join_marks_breaks_and_keeps_hyphenated_words_whole():
    assert join(["IL FA-", "RO DEL PORTO"]) == "IL FARO ‖ DEL PORTO"
    assert join(["UNO", "DUE", "TRE"]) == "UNO ‖ DUE ‖ TRE"


def test_split_uses_marks_or_source_lengths():
    assert split("PRVI DEO ‖ DRUGI DEO", ["AAAA", "BBBB"]) == ["PRVI DEO", "DRUGI DEO"]
    # bez oznake: srazmerno dužini originala, na granici reči
    assert split("JEDAN DVA TRI ČETIRI", ["AAAAAAAAAAAA", "BBBB"]) == ["JEDAN DVA TRI", "ČETIRI"]
    assert split("SAMO", ["AAAA", "BBBB", "CCCC"]) == ["SAMO", "", ""]


def link(client, block, target):
    return client.patch(
        f"/api/blocks/{block['id']}", json={"continues_id": target["id"] if target else None}
    )


def test_link_rules(client):
    page = create_page(client)
    first = add_block(client, page, COLUMN_1, kind="caption")
    second = add_block(client, page, COLUMN_2, y=100, kind="caption")
    third = add_block(client, page, "ALTRO.", y=200, kind="caption")

    assert link(client, first, second).json()["continues_id"] == second["id"]
    assert link(client, third, second).status_code == 409  # drugi već ima prethodnika
    assert link(client, second, first).status_code == 409  # krug
    assert link(client, first, first).status_code == 422
    assert link(client, first, None).json()["continues_id"] is None


def test_chain_is_translated_as_one_text_and_split_back(client, monkeypatch):
    page = create_page(client)
    third = add_block(client, page, "FINE.", kind="caption")
    first = add_block(client, page, COLUMN_1, y=100, kind="caption")
    second = add_block(client, page, COLUMN_2, y=200, kind="caption")
    link(client, first, second)
    requests = []
    answer = [
        {"number": 1, "text": "KRAJ."},
        {
            "number": 2,
            "text": "STARI SVETIONIK SE PALI SVAKE VEČERI I VODI RIBARSKE ČAMCE SA "
            "‖ ISTOKA DO SIGURNE LUKE.",
        },
    ]
    use_remote(monkeypatch, [{"translations": answer}], requests)

    client.post(f"/api/pages/{page['id']}/translate", json={"model": "or:test/model"})
    run_worker(client)

    sent = str(requests)
    assert "PESCATORI DI ‖ LEVANTE" in sent
    by_id = {b["id"]: b["translation"] for b in blocks(client, page)}
    assert by_id[first["id"]] == "STARI SVETIONIK SE PALI SVAKE VEČERI I VODI RIBARSKE ČAMCE SA"
    assert by_id[second["id"]] == "ISTOKA DO SIGURNE LUKE."
    assert by_id[third["id"]] == "KRAJ."


def test_long_caption_without_sentence_end_is_flagged(client):
    page = create_page(client)
    add_block(client, page, COLUMN_1, kind="caption")
    add_block(client, page, COLUMN_2, y=100, kind="caption")
    add_block(
        client,
        page,
        "Grazie a tutti per la passione che ci unisce\nMarco Rossi",
        y=200,
        kind="caption",
    )
    review = client.get(f"/api/pages/{page['id']}/review").json()["blocks"]
    assert [b["maybe_continues"] for b in review] == [True, False, False]  # potpis je kraj


def test_undo_restores_link(client):
    page = create_page(client)
    first = add_block(client, page, COLUMN_1, kind="caption")
    second = add_block(client, page, COLUMN_2, y=100, kind="caption")
    link(client, first, second)
    link(client, first, None)
    client.post(f"/api/pages/{page['id']}/undo")
    assert blocks(client, page)[0]["continues_id"] == second["id"]


def test_cleared_translation_is_filled_again_by_the_chain(client, monkeypatch):
    page = create_page(client)
    first = add_block(client, page, COLUMN_1, kind="caption", translation="STARO")
    second = add_block(client, page, COLUMN_2, y=100, kind="caption", translation="STARO")
    link(client, first, second)
    cleared = client.patch(f"/api/blocks/{second['id']}", json={"translation": ""}).json()
    assert cleared["translation_status"] == "none"  # brisanje nije ručna izmena
    requests = []
    answer = [{"number": 1, "text": "PRVI DEO ‖ DRUGI DEO.", "note": ""}]
    use_remote(monkeypatch, [{"translations": answer}], requests)

    client.post(f"/api/blocks/{first['id']}/translate", json={"model": "or:test/model"})

    assert [b["translation"] for b in blocks(client, page)] == ["PRVI DEO", "DRUGI DEO."]
