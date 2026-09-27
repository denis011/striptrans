def add_entry(client, **fields):
    body = {"source": "Mico", "target": "Mićo", "kind": "name", **fields}
    return client.post("/api/series/1/glossary", json=body)


def test_create_normalizes_and_lists_entries(client):
    response = add_entry(
        client, source="  spirito  con la scure ", target="duh sa sekirom", kind="phrase"
    )

    assert response.status_code == 201
    entry = response.json()
    assert (entry["source"], entry["target"], entry["status"], entry["origin"]) == (
        "SPIRITO CON LA SCURE",
        "DUH SA SEKIROM",
        "approved",
        "manual",
    )
    assert [e["source"] for e in client.get("/api/series/1/glossary").json()] == [
        "SPIRITO CON LA SCURE"
    ]


def test_duplicate_entry_is_rejected(client):
    assert add_entry(client).status_code == 201
    assert add_entry(client, source="mico", target="mićo").status_code == 409


def test_approve_suggestion_and_filter_by_status(client):
    entry = add_entry(client).json()
    client.patch(f"/api/glossary/{entry['id']}", json={"status": "suggested"})

    assert [
        e["id"] for e in client.get("/api/series/1/glossary", params={"status": "suggested"}).json()
    ] == [entry["id"]]
    updated = client.patch(
        f"/api/glossary/{entry['id']}", json={"status": "approved", "target": "mićo!"}
    ).json()
    assert (updated["status"], updated["target"]) == ("approved", "MIĆO!")
    assert client.get("/api/series/1/glossary", params={"status": "suggested"}).json() == []


def test_delete_entry(client):
    entry = add_entry(client).json()

    assert client.delete(f"/api/glossary/{entry['id']}").status_code == 204
    assert client.get("/api/series/1/glossary").json() == []


def test_unknown_series(client):
    assert client.get("/api/series/999/glossary").status_code == 404
    assert (
        client.post("/api/series/999/glossary", json={"source": "A", "target": "B"}).status_code
        == 404
    )
