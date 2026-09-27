import json

from remote_mock import use_remote

from app.services.translation import (
    SourceBlock,
    build_prompt,
    is_too_long,
    parse_translations,
    relevant_glossary,
    shorten,
    translate_blocks,
)

MODEL = "or:test/model"
BLOCKS = [
    SourceBlock(1, "speech", "MICO, ANDIAMO!"),
    SourceBlock(2, "sfx", "SWACK"),
    SourceBlock(3, "caption", "POCO DOPO..."),
]


def fake_llm(monkeypatch, answers: list, requests: list) -> None:
    use_remote(monkeypatch, answers, requests)


def test_prompt_contains_numbered_blocks_glossary_and_context():
    prompt = build_prompt(
        BLOCKS, [("MICO", "MIĆO")], [("RAMON!...", "RAMONE!")], [("AIUTO!", "U POMOĆ!")]
    )

    assert "1. [speech] MICO, ANDIAMO!" in prompt
    assert "2. [sound effect] SWACK" in prompt
    assert "- MICO → MIĆO" in prompt
    assert "- AIUTO! → U POMOĆ!" in prompt
    assert "- RAMON!... → RAMONE!" in prompt


def test_prompt_omits_empty_sections():
    prompt = build_prompt(BLOCKS[:1], [], [], [])

    assert "Glossary" not in prompt and "Previous page" not in prompt and "Examples" not in prompt


def test_relevant_glossary_matches_whole_words_only():
    glossary = [("MICO", "MIĆO"), ("ABE", "EJB"), ("GREYWOOD", "GREJVUD")]

    assert relevant_glossary(glossary, "mico, abete e pini!") == [("MICO", "MIĆO")]


def test_parse_translations_is_defensive():
    response = json.dumps(
        {
            "translations": [
                {"number": 1, "text": "mićo,  idemo!"},
                {"number": 9, "text": "X"},
                {"number": "2", "text": ""},
            ]
        }
    )

    assert parse_translations(response, {1, 2}) == {1: "MIĆO, IDEMO!"}
    assert parse_translations("nije json", {1}) == {}
    assert parse_translations(json.dumps({"translations": "x"}), {1}) == {}


def test_parse_drops_block_marker_and_cyrillic():
    response = json.dumps(
        {
            "translations": [
                {"number": 1, "text": "[SPEECH] MIĆO, IDEMO!"},
                {"number": 2, "text": "(znak ili natpis) ŠERIF"},
                {"number": 3, "text": "ПРЕКОРАЧИО СИ ЗНАК, ЏЕЈН!"},
            ]
        }
    )

    assert parse_translations(response, {1, 2, 3}) == {
        1: "MIĆO, IDEMO!",
        2: "ŠERIF",
        3: "PREKORAČIO SI ZNAK, DŽEJN!",
    }


def test_length_check_allows_short_interjections():
    assert is_too_long("CIAO!", "ZDRAVO!") is False
    assert is_too_long("E' LUI!", "TO JE BAŠ ON, ZAISTA ON!") is True


def test_missing_block_is_translated_separately(monkeypatch):
    requests = []
    answers = [
        {
            "translations": [
                {"number": 1, "text": "MIĆO, IDEMO!"},
                {"number": 3, "text": "MALO KASNIJE..."},
            ]
        },
        {"translations": [{"number": 2, "text": "SCVAK"}]},
    ]

    fake_llm(monkeypatch, answers, requests)
    result = translate_blocks(MODEL, BLOCKS, [("MICO", "MIĆO")], [], [])

    assert result == {1: "MIĆO, IDEMO!", 2: "SCVAK", 3: "MALO KASNIJE..."}
    assert len(requests) == 2
    assert requests[0]["format"]["required"] == ["translations"]
    assert (requests[0]["model"], requests[0]["temperature"]) == ("test/model", 0.2)
    assert "- MICO → MIĆO" in requests[0]["prompt"]
    assert (
        "2. [sound effect] SWACK" in requests[1]["prompt"]
        and "1. [speech]" not in requests[1]["prompt"]
    )


def test_empty_answer_is_retried_without_examples(monkeypatch):
    requests = []
    answers = [
        {"translations": []},
        {"translations": []},
        {"translations": [{"number": 1, "text": "MIĆO, IDEMO!"}]},
    ]
    blocks = BLOCKS[:1]
    examples = [("SI'", "JESTE")]

    fake_llm(monkeypatch, answers, requests)
    result = translate_blocks(MODEL, blocks, [], [("CIAO", "ZDRAVO")], examples)

    assert result == {1: "MIĆO, IDEMO!"}
    assert len(requests) == 3
    assert "JESTE" in requests[1]["prompt"]
    assert "JESTE" not in requests[2]["prompt"] and "ZDRAVO" not in requests[2]["prompt"]


def test_shorten_asks_for_shorter_version(monkeypatch):
    requests = []
    answer = {"translations": [{"number": 1, "text": "MIĆO, AJDE!"}]}

    fake_llm(monkeypatch, [answer], requests)
    result = shorten(MODEL, BLOCKS[0], "MIĆO, HAJDEMO SADA ODAVDE!", [])

    assert result == "MIĆO, AJDE!"
    assert "too long for the balloon: MIĆO, HAJDEMO SADA ODAVDE!" in requests[0]["prompt"]


def test_parse_replaces_croatian_words_with_the_same_endings():
    response = json.dumps(
        {
            "translations": [
                {"number": 1, "text": "TISUĆU MI SKALPOVA!"},
                {"number": 2, "text": "TKO JE TO? NITKO!"},
                {"number": 3, "text": "DVE TISUĆE DOLARA, A NETKO VIČE!"},
            ]
        }
    )

    assert parse_translations(response, {1, 2, 3}) == {
        1: "HILJADU MI SKALPOVA!",
        2: "KO JE TO? NIKO!",
        3: "DVE HILJADE DOLARA, A NEKO VIČE!",
    }


def test_emphasis_markers_are_sent_and_kept_when_carried_over(monkeypatch):
    requests = []
    blocks = [SourceBlock(1, "speech", "*FERMO!*... LASCIA"), SourceBlock(2, "speech", "*BASTA*!")]
    answers = [
        {
            "translations": [
                {"number": 1, "text": "*STANI!*... PUSTI"},
                {"number": 2, "text": "DOSTA!"},
            ]
        }
    ]
    fake_llm(monkeypatch, answers, requests)

    result = translate_blocks(MODEL, blocks, [], [], [])

    assert result == {1: "*STANI!*... PUSTI", 2: "DOSTA!"}
    assert "1. [speech] *FERMO!*... LASCIA" in requests[0]["prompt"]
    assert "asterisks" in requests[0]["prompt"]
