import csv
import io

from factories import create_page


def block(client, page, **fields) -> dict:
    data = {"x": 10, "y": 10, "width": 100, "height": 40, "kind": "speech"} | fields
    created = client.post(f"/api/pages/{page['id']}/blocks", json=data).json()
    changes = {key: fields[key] for key in ("translation",) if key in fields}
    if changes:
        client.patch(f"/api/blocks/{created['id']}", json=changes)
    return created


def test_script_html_has_every_block_in_reading_order(client):
    page = create_page(client)
    block(client, page, text="CIAO!", translation="zdravo!")
    block(client, page, text="CHE DIAVOLO", translation="kog đavola", kind="caption", y=200)

    answer = client.get("/api/projects/1/script")

    assert answer.status_code == 200
    body = answer.text
    assert "CIAO!" in body and "ZDRAVO!" in body
    assert body.index("CIAO!") < body.index("CHE DIAVOLO")  # redosled čitanja
    assert "govor" in body and "naracija" in body
    assert "Strana 1" in body
    assert answer.headers["content-disposition"].startswith("inline")  # otvara se u browseru


def test_script_csv_opens_as_a_table(client):
    page = create_page(client)
    block(client, page, text="CIAO!", translation="zdravo!")

    answer = client.get("/api/projects/1/script", params={"format": "csv"})

    assert answer.headers["content-disposition"].startswith("attachment")
    assert answer.content.startswith(b"\xef\xbb\xbf")  # BOM, da Excel pročita naša slova
    rows = list(csv.DictReader(io.StringIO(answer.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0]["strana"] == "1"
    assert rows[0]["original"] == "CIAO!"
    assert rows[0]["prevod"] == "ZDRAVO!"
    assert rows[0]["vrsta"] == "govor"
    assert rows[0]["status"] == "izmenjeno"


def test_skipped_pages_stay_out_unless_asked_for(client):
    page = create_page(client)
    block(client, page, text="CIAO!", translation="zdravo!")
    client.patch(f"/api/pages/{page['id']}", json={"skip": True})

    assert "CIAO!" not in client.get("/api/projects/1/script").text
    assert "CIAO!" in client.get("/api/projects/1/script", params={"skipped": True}).text


def test_blocks_without_any_text_are_left_out(client):
    page = create_page(client)
    block(client, page, text="")
    block(client, page, text="CIAO!", y=200)

    rows = list(
        csv.DictReader(
            io.StringIO(
                client.get("/api/projects/1/script", params={"format": "csv"}).content.decode(
                    "utf-8-sig"
                )
            ),
            delimiter=";",
        )
    )

    assert [row["original"] for row in rows] == ["CIAO!"]
    assert rows[0]["status"] == "bez prevoda"


def test_unknown_format_is_rejected(client):
    create_page(client)

    assert client.get("/api/projects/1/script", params={"format": "pdf"}).status_code == 400
