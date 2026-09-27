import io

import httpx
from factories import create_page, jpeg_bytes
from llama_mock import llama_client, ocr_server, refused, reply
from PIL import Image

from app.services.llm_base import LlmError
from app.services.ocr import (
    clean_output,
    crop_block,
    fix_punctuation,
    needs_review,
    prompt_for,
    uppercase_lettering,
)


def add_block(client, page) -> dict:
    body = {"x": 10, "y": 10, "width": 100, "height": 40}
    return client.post(f"/api/pages/{page['id']}/blocks", json=body).json()


def test_clean_output_removes_decorations():
    assert clean_output("```text\nText: L'UOMO CHE\n\n  STAVATE  \n```") == "L'UOMO CHE\nSTAVATE"
    assert clean_output('"SCERIFFO!"') == "SCERIFFO!"
    assert clean_output("E' APPENA\nARRIVATO") == "E' APPENA\nARRIVATO"


def test_common_punctuation_fixes():
    raw = "PERICOLI IMMEDIA- TI!\nE·LUI! E'' UN\nRAMON!/..."

    fixed = "PERICOLI IMMEDIA-\nTI!\nE'LUI! E' UN\nRAMON!..."
    assert fix_punctuation(raw) == fixed


def test_mostly_uppercase_text_becomes_uppercase():
    assert uppercase_lettering("Sí, Nick!...\nUN'AQUILA O") == "SÍ, NICK!...\nUN'AQUILA O"
    assert uppercase_lettering("The image shows a cowboy") == "The image shows a cowboy"


def test_needs_review():
    assert needs_review("SCERIFFO!") is False
    assert needs_review("THUD") is False
    assert needs_review("") is True
    assert needs_review("The image shows a cowboy") is True
    assert needs_review("警长") is True


def test_prompt_for_language():
    assert "in Italian" in prompt_for()
    assert "in Serbian (Latin script)" in prompt_for("sr")


def test_crop_adds_margin_and_upscales_small_blocks(tmp_path):
    path = tmp_path / "p.jpg"
    path.write_bytes(jpeg_bytes(size=(1000, 1000)))

    crop = Image.open(io.BytesIO(crop_block(path, 100, 100, 200, 50)))

    # margina 20 px levo/desno i 12 px gore/dole → 240×74, pa uvećanje na visinu 200
    assert crop.size == (649, 200)


def test_crop_is_clamped_to_page(tmp_path):
    path = tmp_path / "p.jpg"
    path.write_bytes(jpeg_bytes(size=(1000, 1000)))

    crop = Image.open(io.BytesIO(crop_block(path, 950, 0, 50, 300)))

    assert crop.size == (62, 330)


def test_ocr_block_saves_text_and_sends_crop(make_client):
    requests = []
    client = make_client(ocr_server(requests))
    block = add_block(client, create_page(client))

    response = client.post(f"/api/blocks/{block['id']}/ocr", json={"model": "qwen2.5vl:7b"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["text"], body["ocr_text"], body["ocr_model"]) == (
        "SCERIFFO!",
        "SCERIFFO!",
        "qwen2.5vl:7b",
    )
    assert body["needs_review"] is False
    [sent] = requests
    assert (sent["temperature"], sent["max_tokens"]) == (0, 400)
    assert Image.open(io.BytesIO(sent["images"][0])).format == "PNG"
    assert sent["model"] == "qwen2.5vl:7b"  # Ollama bira model po imenu


def test_ocr_uses_default_model_and_flags_suspicious_text(make_client, settings):
    requests = []
    client = make_client(ocr_server(requests, response="I cannot read this image."))
    block = add_block(client, create_page(client))

    body = client.post(f"/api/blocks/{block['id']}/ocr").json()

    assert body["ocr_model"] == settings.ocr_model
    assert body["needs_review"] is True


def test_ocr_returns_502_when_llama_server_is_down(make_client):
    client = make_client(refused)
    block = add_block(client, create_page(client))

    assert client.post(f"/api/blocks/{block['id']}/ocr", json={}).status_code == 502


def test_ocr_models_lists_the_model_of_the_server(make_client, settings):
    client = make_client(ocr_server([]))

    body = client.get("/api/ocr/models").json()

    assert body["default_model"] == settings.ocr_model
    assert [(m["name"], m["capabilities"]) for m in body["models"]] == [
        ("qwen2.5vl:7b", ["completion", "vision"])
    ]


def test_ocr_models_returns_502_when_llama_server_is_down(make_client):
    assert make_client(refused).get("/api/ocr/models").status_code == 502


def test_loading_server_is_not_a_model_failure():
    """503 dok se model učitava: posao čeka; 500 na bloku: model nije uspeo, blok ide na proveru."""

    def loading(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "Loading model"}})

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "failed"}})

    for handler, status, model_failed in ((loading, None, False), (failing, 500, True)):
        try:
            llama_client(handler).generate("x", "m")
        except LlmError as exc:
            assert (exc.status, exc.model_failed) == (status, model_failed)
        else:
            raise AssertionError("očekivana greška")


def test_generate_sends_images_before_prompt_and_reads_timings():
    requests = []
    result = llama_client(ocr_server(requests)).generate("čitaj", "m", images=[b"png"])

    content = requests[0]["messages"][0]["content"]
    assert [part["type"] for part in content] == ["image_url", "text"]
    assert requests[0]["images"] == [b"png"]
    assert (result.response, result.prompt_tokens_per_second) == ("```\nSCERIFFO!\n```", 160.0)


def test_empty_answer_is_an_empty_text():
    result = llama_client(lambda request: reply(None)).generate("x", "m")

    assert result.response == ""


def test_ocr_uses_language_of_the_series(make_client):
    requests = []
    client = make_client(ocr_server(requests))
    series = client.post("/api/series", json={"name": "Ramon SR", "source_lang": "sr"}).json()
    block = add_block(client, create_page(client, series_id=series["id"]))

    client.post(f"/api/blocks/{block['id']}/ocr", json={"model": "qwen2.5vl:7b"})

    assert "in Serbian" in requests[0]["prompt"]
