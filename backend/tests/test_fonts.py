import io

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from app.services.fonts import BUILTIN, BUILTIN_DIR, REQUIRED, inspect_font


def make_font(chars: str, empty: str = "") -> bytes:
    """Mali TTF: kvadrat za svako slovo iz `chars`; slova iz `empty` imaju prazan glif."""
    names = [".notdef"] + [f"g{ord(c)}" for c in chars]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(c): f"g{ord(c)}" for c in chars})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        if name == ".notdef" or chr(int(name[1:])) not in empty:
            pen.moveTo((100, 0))
            pen.lineTo((100, 700))
            pen.lineTo((500, 700))
            pen.lineTo((500, 0))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 100) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Proba", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    buffer = io.BytesIO()
    builder.save(buffer)
    return buffer.getvalue()


def upload(client, data: bytes, kind="dialogue"):
    return client.post(
        "/api/fonts", data={"kind": kind}, files={"file": ("font.ttf", data, "font/ttf")}
    )


def test_builtin_fonts_have_all_serbian_letters():
    for font in BUILTIN:
        assert inspect_font((BUILTIN_DIR / font.filename).read_bytes())[1] == [], font.key


def test_empty_glyphs_count_as_missing():
    name, missing = inspect_font(make_font(REQUIRED, empty="ĐŽ"))

    assert name == "Proba" and missing == ["Đ", "Ž"]


def test_list_contains_builtin_fonts_with_files(client):
    fonts = client.get("/api/fonts").json()

    keys = [font["key"] for font in fonts]
    assert keys[:1] == ["comic-neue-bold"] and "bangers" in keys
    response = client.get(fonts[0]["url"])
    assert response.status_code == 200 and response.content[:4] == b"\x00\x01\x00\x00"


def test_upload_accepts_complete_font_and_series_can_use_it(client):
    created = upload(client, make_font(REQUIRED), kind="sfx")

    assert created.status_code == 201
    font = created.json()
    assert (font["name"], font["kind"], font["builtin"]) == ("Proba", "sfx", False)
    assert "?v=" in font["url"]  # verzija fajla u adresi: keš ne vraća stari font za isti ključ
    assert client.get(font["url"]).status_code == 200
    series = client.patch("/api/series/1", json={"sfx_font": font["key"]}).json()
    assert series["sfx_font"] == font["key"]

    assert client.delete(f"/api/fonts/{font['key']}").status_code == 204
    assert client.get("/api/series").json()[0]["sfx_font"] is None
    assert client.get(font["url"]).status_code == 404


def test_upload_rejects_font_without_serbian_letters(client):
    response = upload(client, make_font(REQUIRED.replace("Đ", "")))

    assert response.status_code == 400 and "Đ" in response.json()["detail"]
    assert upload(client, b"nije font uopste").status_code == 400


def test_series_rejects_unknown_font(client):
    assert client.patch("/api/series/1", json={"dialogue_font": "nema-ga"}).status_code == 400
    assert client.patch("/api/series/1", json={"dialogue_font": "bangers"}).status_code == 200
    assert client.delete("/api/fonts/bangers").status_code == 404  # ugrađeni se ne brišu


def test_series_option_captions_in_italics(client):
    series = client.get("/api/series").json()[0]
    assert series["caption_italic"] is False

    updated = client.patch(f"/api/series/{series['id']}", json={"caption_italic": True}).json()
    assert updated["caption_italic"] is True
    # izmena fonta ne dira opciju, a opcija ne traži font
    kept = client.patch(f"/api/series/{series['id']}", json={"dialogue_font": None}).json()
    assert kept["caption_italic"] is True
