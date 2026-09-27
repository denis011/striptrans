from factories import create_page


def make_block(client):
    page = create_page(client)
    body = {"x": 10, "y": 10, "width": 200, "height": 60, "text": "CIAO!"}
    return client.post(f"/api/pages/{page['id']}/blocks", json=body).json()


def test_block_starts_with_automatic_lettering(client):
    assert make_block(client)["style"] is None


def test_style_is_saved_with_defaults_and_can_be_reset(client):
    block = make_block(client)

    styled = client.patch(
        f"/api/blocks/{block['id']}", json={"style": {"scale": 1.2, "dx": -8, "rotation": 12}}
    ).json()

    assert styled["style"] == {
        "scale": 1.2,
        "dx": -8,
        "dy": 0,
        "rotation": 12,
        "align": "center",
        "line_spacing": 1,
        "font": None,
        "fit": "fill",
        "letter_spacing": 0,
        "letters": {},
        "opaque": None,
        "color": None,
        "outline_color": None,
        "outline_width": None,
        "fill_box": False,
        "emphasis": False,
        "letter_fonts": {},
        "cover": False,
    }
    other = client.patch(f"/api/blocks/{block['id']}", json={"translation": "zdravo"}).json()
    assert other["style"]["scale"] == 1.2  # druge izmene ne diraju stil
    reset = client.patch(f"/api/blocks/{block['id']}", json={"style": None}).json()
    assert reset["style"] is None


def test_style_values_are_validated(client):
    block = make_block(client)

    assert (
        client.patch(f"/api/blocks/{block['id']}", json={"style": {"align": "justify"}}).status_code
        == 200
    )
    for bad in ({"scale": 5}, {"rotation": 400}, {"align": "block"}, {"line_spacing": 0.1}):
        response = client.patch(f"/api/blocks/{block['id']}", json={"style": bad})
        assert response.status_code == 422, bad


def test_manual_line_breaks_in_translation_are_kept(client):
    block = make_block(client)

    updated = client.patch(f"/api/blocks/{block['id']}", json={"translation": "to je\non!"}).json()

    assert updated["translation"] == "TO JE\nON!"


def test_text_and_outline_colour_are_saved_and_checked(client):
    block = make_block(client)

    styled = client.patch(
        f"/api/blocks/{block['id']}",
        json={"style": {"color": "#ffd400", "outline_color": "#D7261E", "outline_width": 0.1}},
    ).json()

    assert styled["style"]["color"] == "#ffd400"
    assert styled["style"]["outline_color"] == "#D7261E"
    assert styled["style"]["outline_width"] == 0.1
    for bad in ({"color": "yellow"}, {"color": "#fff"}, {"outline_width": 0.9}):
        response = client.patch(f"/api/blocks/{block['id']}", json={"style": bad})
        assert response.status_code == 422, bad
