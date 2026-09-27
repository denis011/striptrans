import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.models import TextBlock
from app.services import emphasis
from app.services.glossary_suggest import flatten
from app.services.translation import emphasis_count, is_too_long, keep_emphasis

FONT = ImageFont.load_default(size=40)
ELLIPSE = [[0, 50], [50, 0], [100, 50], [50, 100]]  # romb: nije pravougaonik naracije


def lettering(lines: list[tuple[str, bool]], width: int = 700) -> Image.Image:
    """Strana sa redovima teksta; naglašen red je podebljan (deblji potez) i ukošen."""
    page = Image.new("L", (width, 60 * len(lines) + 80), 255)
    for row, (text, bold) in enumerate(lines):
        layer = Image.new("L", (width, 60), 0)
        ImageDraw.Draw(layer).text(
            (20, 5), text, font=FONT, fill=255, stroke_width=2 if bold else 0
        )
        if bold:  # smicanje udesno za ~15°
            layer = layer.transform(
                layer.size, Image.AFFINE, (1, 0.27, -12, 0, 1, 0), Image.BILINEAR
            )
        page.paste(0, (0, 40 + row * 60), layer)
    return page


def analyze(page: Image.Image, text: str, polygon=ELLIPSE) -> emphasis.Emphasis:
    return emphasis.analyze(page, (10, 35, page.width - 20, page.height - 70), text, polygon)


def test_upright_text_is_not_emphasized():
    page = lettering([("HANNO UNA CAMERA", False), ("SOPRA IL SALOON", False)])

    assert analyze(page, "HANNO UNA CAMERA\nSOPRA IL SALOON") == emphasis.Emphasis()


def test_bold_slanted_block_is_a_shout():
    page = lettering([("MALEDETTO", True), ("VIGLIACCO!", True)])

    assert analyze(page, "MALEDETTO\nVIGLIACCO!").block is True


def test_narration_box_is_never_emphasized():
    page = lettering([("MALEDETTO", True)])
    box = [[0, 0], [100, 0], [100, 100], [0, 100]]

    assert analyze(page, "MALEDETTO", box) == emphasis.Emphasis()


def test_emphasized_line_marks_its_words():
    page = lettering([("E' UN AMICO", False), ("ANCHE LUI", False), ("ADESSO BASTA!", True)])

    found = analyze(page, "E' UN AMICO\nANCHE LUI\nADESSO BASTA!")

    assert (found.block, found.words) == (False, [(2, 0), (2, 1)])


def test_mark_wraps_neighbouring_words_once():
    text = "PER MILLE\nSCALPI!... JACK\nBROWN E' ANCO-\nRA VIVO?"
    words = [(1, 1), (2, 0), (2, 1), (2, 2), (3, 0), (3, 1)]

    assert emphasis.mark(text, words) == (
        "PER MILLE\nSCALPI!... *JACK*\n*BROWN E' ANCO-*\n*RA VIVO?*"
    )


def test_flatten_drops_markers_except_for_translation():
    text = "SCALPI!... *JACK*\n*BROWN E' ANCO-*\n*RA VIVO?*"

    assert flatten(text) == "SCALPI!... JACK BROWN E' ANCORA VIVO?"
    assert flatten(text, emphasis=True) == "SCALPI!... *JACK* *BROWN E' ANCORA VIVO?*"


def test_translation_keeps_markers_only_when_all_are_carried_over():
    source = "*FERMO!*... LASCIA CHE SIA IO"

    assert keep_emphasis(source, "*STANI!*... PUSTI MENE") == "*STANI!*... PUSTI MENE"
    assert keep_emphasis(source, "*STANI!... PUSTI* *MENE*") == "STANI!... PUSTI MENE"
    assert keep_emphasis(source, "*STANI!... PUSTI MENE") == "STANI!... PUSTI MENE"
    assert emphasis_count("*A* I *B*") == 2
    assert not is_too_long("*AH!*", "*AAH!*")  # zvezdice se ne računaju u dužinu


def balloon(page: Image.Image, shape: str = "ellipse") -> tuple[Image.Image, TextBlock]:
    """Tekst u oblačiću (elipsa) ili u okviru naracije (pravougaonik), i blok oko teksta."""
    canvas = Image.new("L", (page.width + 240, page.height + 240), 255)
    canvas.paste(page, (120, 120))
    draw = ImageDraw.Draw(canvas)
    outline = (20, 20, canvas.width - 20, canvas.height - 20)
    (draw.ellipse if shape == "ellipse" else draw.rectangle)(outline, outline=0, width=4)
    block = TextBlock(
        kind="speech", x=130, y=155, width=page.width - 20, height=page.height - 70, text=""
    )
    return canvas, block


def test_apply_sets_block_emphasis_and_skips_narration_sfx_and_marked():
    page = lettering([("MALEDETTO", True), ("VIGLIACCO!", True)])
    shout_page, shout = balloon(page)
    narration_page, narration = balloon(page, "rectangle")
    shout.text = narration.text = "MALEDETTO\nVIGLIACCO!"
    sfx = TextBlock(kind="sfx", text="SWACK", x=130, y=155, width=100, height=50)
    marked = TextBlock(kind="speech", text="*MALEDETTO*", x=130, y=155, width=300, height=50)
    gray = np.asarray(shout_page)  # samo za čitanje: apply ga ne sme menjati

    assert emphasis.apply(shout, shout_page, gray) is True
    assert shout.style == {"emphasis": True}
    assert emphasis.apply(narration, narration_page, np.asarray(narration_page)) is False
    assert emphasis.apply(sfx, shout_page, gray) is False  # onomatopeje imaju svoj izgled
    assert emphasis.apply(marked, shout_page, gray) is False  # ručne oznake ostaju


def test_punctuation_alone_is_not_marked():
    page = lettering([("PENSI DI ESSERE", False), ("AL CIRCO", False), ("?! ?", True)])

    assert analyze(page, "PENSI DI ESSERE\nAL CIRCO\n?! ?").words == []
