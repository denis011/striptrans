from factories import create_page
from remote_mock import use_remote

from app.services.glossary_suggest import extract_entries, flatten
from worker.main import run_once

LLM_ENTRIES = [
    {"source": "Mico", "target": "Mićo", "kind": "name"},
    {"source": "AH!", "target": "AH!", "kind": "sfx"},  # isto u oba jezika
    {"source": "GREYWOOD", "target": "GREJVUD", "kind": "place"},  # nema ga u tekstu
    {"source": "ANDIAMO", "target": "IDEMO", "kind": "nešto"},  # nepoznata vrsta
]


def llm(monkeypatch, requests: list, entries=LLM_ENTRIES) -> None:
    use_remote(monkeypatch, [{"entries": entries}] * 10, requests)


def test_flatten_joins_hyphenated_lines():
    assert flatten("HILJADU MI BUBNJE-\nVA!\nsmiri se") == "HILJADU MI BUBNJEVA! SMIRI SE"


def test_extract_entries_keeps_only_real_translations(monkeypatch):
    requests = []
    pairs = [("MICO, ANDIAMO!", "MIĆO, IDEMO!"), ("AH!", "AH!")]

    llm(monkeypatch, requests)
    entries = extract_entries("or:test/model", pairs)

    assert entries == [("MICO", "MIĆO", "name")]
    assert requests[0]["format"]["required"] == ["entries"]
    assert "1. IT: MICO, ANDIAMO! | SR: MIĆO, IDEMO!" in requests[0]["prompt"]


def test_suggest_job_adds_suggestions_from_aligned_pages(client, monkeypatch):
    original, reference = create_page(client), create_page(client)
    box = {"x": 50, "y": 50, "width": 200, "height": 80}
    client.post(f"/api/pages/{original['id']}/blocks", json={**box, "text": "MICO, ANDIAMO!"})
    client.post(f"/api/pages/{reference['id']}/blocks", json={**box, "text": "MIĆO, IDEMO!"})
    projects = client.get("/api/projects").json()
    reference_id, original_id = projects[0]["id"], projects[1]["id"]

    job = client.post(
        "/api/series/1/glossary/suggest",
        json={
            "project_id": original_id,
            "reference_project_id": reference_id,
            "model": "or:test/model",
        },
    ).json()
    state = client.app.state
    llm(monkeypatch, [])
    run_once(state.session_factory, "w1", state.settings)

    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "done", job["error"]
    assert job["result"] == {"pages": 1, "found": 1, "added": 1}
    [entry] = client.get("/api/series/1/glossary", params={"status": "suggested"}).json()
    assert (entry["source"], entry["target"], entry["origin"], entry["occurrences"]) == (
        "MICO",
        "MIĆO",
        "reference",
        1,
    )
