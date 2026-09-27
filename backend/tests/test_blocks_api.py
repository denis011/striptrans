import pytest
from factories import jpeg_bytes, zip_bytes
from sqlalchemy import func, select

from app.models import TextBlock
from worker.main import run_once


@pytest.fixture
def page(client):
    project = client.post("/api/projects", json={"series_id": 1}).json()
    archive = zip_bytes([("1.jpg", jpeg_bytes(size=(600, 800)))])
    client.post(
        f"/api/projects/{project['id']}/imports",
        data={"kind": "original"},
        files=[("files", ("a.cbz", archive, "application/zip"))],
    )
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)
    return client.get(f"/api/projects/{project['id']}/pages").json()[0]


def add_block(client, page, **fields) -> dict:
    body = {"x": 10, "y": 10, "width": 100, "height": 50, **fields}
    response = client.post(f"/api/pages/{page['id']}/blocks", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def block_list(client, page) -> list[dict]:
    return client.get(f"/api/pages/{page['id']}/blocks").json()


def test_create_and_list_blocks(client, page):
    first = add_block(client, page, text="SCERIFFO!")
    second = add_block(client, page, kind="thought")

    assert [(b["id"], b["position"]) for b in block_list(client, page)] == [
        (first["id"], 1),
        (second["id"], 2),
    ]
    assert (first["kind"], first["source"], first["text"]) == ("speech", "manual", "SCERIFFO!")
    assert second["kind"] == "thought"


def test_block_is_clamped_to_page(client, page):
    block = add_block(client, page, x=550, y=790, width=200, height=100)

    assert (block["x"], block["y"], block["width"], block["height"]) == (550, 790, 50, 10)


def test_update_block(client, page):
    block = add_block(client, page)

    response = client.patch(
        f"/api/blocks/{block['id']}",
        json={"x": 20, "width": 150, "kind": "sfx", "text": "THUD", "needs_review": True},
    )

    updated = response.json()
    assert (updated["x"], updated["width"], updated["kind"], updated["text"]) == (
        20,
        150,
        "sfx",
        "THUD",
    )
    assert updated["needs_review"] is True
    assert client.patch(f"/api/blocks/{block['id']}", json={"kind": "oblak"}).status_code == 422


def test_delete_block_renumbers(client, page):
    first, second, third = (add_block(client, page) for _ in range(3))

    assert client.delete(f"/api/blocks/{first['id']}").status_code == 204

    assert [(b["id"], b["position"]) for b in block_list(client, page)] == [
        (second["id"], 1),
        (third["id"], 2),
    ]


def test_reorder_blocks(client, page):
    ids = [add_block(client, page)["id"] for _ in range(3)]
    url = f"/api/pages/{page['id']}/blocks/order"

    assert [b["id"] for b in client.put(url, json={"block_ids": ids[::-1]}).json()] == ids[::-1]
    assert [b["id"] for b in block_list(client, page)] == ids[::-1]
    assert client.put(url, json={"block_ids": ids[:2]}).status_code == 400


def test_merge_blocks(client, page):
    first = add_block(client, page, x=10, y=10, width=100, height=50, text="L'UOMO CHE")
    second = add_block(client, page, x=50, y=100, width=100, height=50, text="STAVATE ASPETTANDO")
    third = add_block(client, page, x=300, y=300)
    url = f"/api/pages/{page['id']}/blocks/merge"

    blocks = client.post(url, json={"block_ids": [second["id"], first["id"]]}).json()

    assert [(b["id"], b["position"]) for b in blocks] == [(first["id"], 1), (third["id"], 2)]
    merged = blocks[0]
    assert (merged["x"], merged["y"], merged["width"], merged["height"]) == (10, 10, 140, 140)
    assert merged["text"] == "L'UOMO CHE\nSTAVATE ASPETTANDO"
    assert client.post(url, json={"block_ids": [third["id"]]}).status_code == 400


def test_duplicate_goes_right_after_original(client, page):
    first = add_block(client, page, text="A")
    second = add_block(client, page, text="B")

    copy = client.post(f"/api/blocks/{first['id']}/duplicate").json()

    assert (copy["x"], copy["y"], copy["text"], copy["position"]) == (30, 30, "A", 2)
    assert [b["id"] for b in block_list(client, page)] == [first["id"], copy["id"], second["id"]]


def test_auto_order_reads_rows(client, page):
    right = add_block(client, page, x=300, y=10)
    bottom = add_block(client, page, x=10, y=400)
    left = add_block(client, page, x=10, y=20)

    blocks = client.post(f"/api/pages/{page['id']}/blocks/auto-order").json()

    assert [b["id"] for b in blocks] == [left["id"], right["id"], bottom["id"]]


def test_page_flags(client, page):
    response = client.patch(f"/api/pages/{page['id']}", json={"skip": True, "ocr_reviewed": True})

    assert (response.json()["skip"], response.json()["ocr_reviewed"]) == (True, True)


def test_deleting_page_deletes_its_blocks(client, page):
    add_block(client, page)

    client.delete(f"/api/pages/{page['id']}")

    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TextBlock)) == 0
