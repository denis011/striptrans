from tools.metrics import edit_distance, match_boxes, normalize_text, order_is_correct, overlap


def test_normalize_joins_hyphenated_words_and_unifies_accents():
    assert (
        normalize_text("E' APPENA ARRI-\nVATO IN PAESE !... E,\nGIÀ")
        == "E' APPENA ARRIVATO IN PAESE!... E, GIA'"
    )
    assert normalize_text("PERCHE`?") == normalize_text("perchè ?") == "PERCHE'?"


def test_edit_distance():
    assert edit_distance("SCERIFFO!", "SCERIFFO!") == 0
    assert edit_distance("SEGUI-TEMI!", "SEGUITEMI!") == 1
    assert edit_distance("", "AH!") == 3


def test_match_boxes_tolerates_looser_boxes():
    gold = [(100, 100, 200, 100), (500, 500, 100, 50)]
    predicted = [(510, 505, 80, 40), (90, 90, 230, 130), (900, 900, 50, 50)]

    assert match_boxes(predicted, gold) == {0: 1, 1: 0}
    assert overlap((0, 0, 10, 10), (20, 20, 5, 5)) == 0


def test_order_is_checked_only_on_considered_blocks():
    assert order_is_correct({0: 0, 1: 2, 2: 1}, considered={0, 2}) is True
    assert order_is_correct({0: 1, 1: 0}, considered={0, 1}) is False


def test_chrf_is_100_for_identical_and_lower_for_different_text():
    from tools.metrics import chrf

    assert chrf(["PRATITE ME!"], ["PRATITE ME!"]) == 100.0
    close = chrf(["HVALA BOGU ŠTO SI OVDE!"], ["HVALA NEBESIMA ŠTO SI TU!"])
    far = chrf(["MA... ŠERIF!"], ["JESTE, ŠERIFE!"])
    assert 0 < far < close < 100


def test_glossary_term_allows_case_endings():
    from tools.metrics import uses_glossary_term

    assert uses_glossary_term("RAMONE! MIĆO, STANI!", "RAMON")
    assert uses_glossary_term("DUHA SA SEKIROM", "DUH SA SEKIROM")
    assert not uses_glossary_term("ZDRAVO, MICO!", "MIĆO")


def test_non_serbian_words_catches_croatian_and_ijekavian_forms():
    from tools.metrics import non_serbian_words

    assert non_serbian_words("TISUĆU MI SKALPOVA! TKO JE TO?") == ["TISUĆU", "TKO"]
    assert non_serbian_words("uvijek je bio ovdje prije") == ["UVIJEK", "OVDJE", "PRIJE"]
    serbian = "HILJADU MU SKALPOVA! KO JE TO? NIJE UVEK OVDE, PIJE VERU. PRIJEM."
    assert non_serbian_words(serbian) == []
