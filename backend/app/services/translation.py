"""Prevod stranice preko OpenRouter-a: prompt sa kontekstom i glosarom, strukturisan izlaz."""

import json
import re
from dataclasses import dataclass

from app.services import llm

MAX_TOKENS = 2048
TEMPERATURE = 0.2
MAX_LENGTH_RATIO = 1.3  # prevod duži od toga (u odnosu na original) verovatno ne staje u oblačić
MIN_LENGTH = 10  # kratki uzvici („AIUTO!" → „U POMOĆ!") smeju da budu duži

KIND_NAMES = {
    "speech": "speech",
    "thought": "thought",
    "caption": "caption",
    "sfx": "sound effect",
    "other": "sign or title",
    "title": "story title",
}

# Tehnički deo uputstva: ne menja se iz aplikacije, jer od njega zavise numeracija, kolone (‖),
# naglasak (*…*), jezik i pismo. Stil prevoda je poseban tekst (DEFAULT_STYLE ili stil korisnika).
INSTRUCTIONS = """You are a professional translator of Italian comics into Serbian.
Translate every numbered text block of the page from Italian into Serbian.
Rules:
- Serbian Latin script, ekavian, UPPERCASE as in comic lettering (use Č, Ć, Ž, Š, Đ).
- Serbian, never Croatian or Bosnian words: HILJADU (not TISUĆU), KO (not TKO), TAČNO (not
  TOČNO), NEDELJA (not TJEDAN), VOZ, HLEB, PORODICA; ekavian forms only: UVEK, OVDE, GDE, VREME.
- Write the names of story characters as they are pronounced, in Serbian letters (BODOCZY → BODOČI,
  LAJOS → LAJOŠ), unless the glossary gives another form; names of real authors stay as written.
- Never write Cyrillic: not a single letter, not a single word.
- The marker in front of each block ([speech], [caption], [sound effect]...) tells you the kind
  of the block; never copy it into the translation and never translate it.
- Keep each translation about as long as the original: it must fit the same balloon.
- Use the glossary translations exactly for names, places and expressions.
- The lettering writes accents as an apostrophe after the vowel: E' = È (is), SI' = SÌ (yes),
  PERCHE' = PERCHÉ, GIA' = GIÀ, PUO' = PUÒ; a real apostrophe stays inside words (L'UOMO, PO').
- Words between asterisks (*ADESSO BASTA*) are emphasized (bold) in the original: put asterisks
  around the Serbian words that carry the same emphasis (*SAD JE DOSTA*), the same number of
  times; never add asterisks anywhere else.
- Translate each block separately and keep the numbering; do not merge or split blocks.
- The mark ‖ inside a block shows where the text continues in the next column or balloon:
  translate the whole block as one text and put exactly the same number of ‖ marks at the
  corresponding places of the translation, so that each part fits its own column.
- The translation goes into the balloon as it is: never add explanations or notes in brackets.
  If a pun or a cultural reference cannot be carried over, explain it briefly in Serbian in
  "note" (for the proofreader); otherwise leave "note" empty."""

# Podrazumevani stil prevoda; menja se na strani Podešavanja (tamo je i povratak na ovaj)
DEFAULT_STYLE = """- Natural, lively spoken Serbian as in the classic published Serbian comic
  editions, never a literal, word-for-word translation: every line must sound natural and
  dramatic read aloud.
- Captions (narration): a narrative, slightly old-fashioned and atmospheric tone
  (U MEĐUVREMENU..., DOK JE NOĆ PADALA NA ŠUMU...).
- Dialogue: living spoken language that fits the character who speaks: comic characters are
  comic, heroes calm and firm, bandits rough and coarse.
- Be concise: if the original is long, shorten it and keep the meaning and the expressiveness.
- Exclamations and curses as in classic comics, never word for word (STO MU GROMOVA!,
  PROKLETSTVO!, GROM I PAKAO!, DO ĐAVOLA!).
- Use the vocative case when a character is addressed (RAMONE!, MIĆO!, TODE!, ŠERIFE!).
- Keep short interjections such as AH! or UNGH! unchanged."""


@dataclass
class Style:
    """Stil prevoda: opšti tekst stila i uputstvo serijala (likovi, uzrečice), oba neobavezna."""

    text: str = DEFAULT_STYLE
    series_notes: str = ""


SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "text": {"type": "string"},
                    "note": {"type": "string"},  # igra reči ili kulturna referenca, za lekturu
                },
                "required": ["number", "text", "note"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,  # OpenAI u strogom režimu traži ovo na svakom objektu
}

Pairs = list[tuple[str, str]]


@dataclass
class SourceBlock:
    number: int
    kind: str
    text: str  # u jednom redu, spojene rastavljene reči


def lettering(text: str) -> str:
    return " ".join(text.upper().split())


# Modeli povremeno odgovore ćirilicom; radimo samo latinicu, pa se preslovljava (velika slova).
CYRILLIC = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z",
    "И": "I", "Ј": "J", "К": "K", "Л": "L", "Љ": "LJ", "М": "M", "Н": "N", "Њ": "NJ", "О": "O",
    "П": "P", "Р": "R", "С": "S", "Т": "T", "Ћ": "Ć", "У": "U", "Ф": "F", "Х": "H", "Ц": "C",
    "Ч": "Č", "Џ": "DŽ", "Ш": "Š",
    # ruska slova koja se povremeno provuku
    "Ё": "JO", "Щ": "ŠĆ", "Ъ": "", "Ы": "I", "Ь": "", "Э": "E", "Ю": "JU", "Я": "JA",
}  # fmt: skip

BLOCK_MARKER = re.compile(r"^\s*[\[(][^\]\n)]{0,40}[\])]\s*")


def to_latin(text: str) -> str:
    return "".join(CYRILLIC.get(char, char) for char in text)


# hrvatske reči koje model uporno piše (PER MILLE SCALPI → „TISUĆU“), a srpska zamena ima iste
# nastavke; ostale ijekavske i hrvatske oblike samo javlja lektura (spellcheck.non_serbian_words)
CROATIAN = [
    (re.compile(r"\bTISUĆ"), "HILJAD"),
    (re.compile(r"\bTKO\b"), "KO"),
    (re.compile(r"\bNETKO\b"), "NEKO"),
    (re.compile(r"\bNITKO\b"), "NIKO"),
]


def serbian_forms(text: str) -> str:
    for pattern, serbian in CROATIAN:
        text = pattern.sub(serbian, text)
    return text


def relevant_glossary(glossary: Pairs, page_text: str) -> Pairs:
    """Stavke glosara koje se javljaju na stranici (kao cele reči)."""
    text = lettering(page_text)
    return [
        (source, target)
        for source, target in glossary
        if re.search(rf"(?<![A-ZÀ-Ý]){re.escape(source)}(?![A-ZÀ-Ý])", text)
    ]


def build_prompt(
    blocks: list[SourceBlock],
    glossary: Pairs,
    context: Pairs,
    examples: Pairs,
    style: Style | None = None,
) -> str:
    style = style or Style()
    parts = [INSTRUCTIONS]
    if style.text.strip():
        parts.append("Translation style:\n" + style.text.strip())
    if style.series_notes.strip():
        parts.append("Notes for this comic series:\n" + style.series_notes.strip())
    if glossary:
        parts.append(
            "Glossary (Italian → Serbian):\n" + "\n".join(f"- {s} → {t}" for s, t in glossary)
        )
    if examples:
        parts.append(
            "Examples from the published Serbian edition:\n"
            + "\n".join(f"- {s} → {t}" for s, t in examples)
        )
    if context:
        parts.append(
            "Previous page, already translated (for context only):\n"
            + "\n".join(f"- {s} → {t}" for s, t in context)
        )
    page = "\n".join(f"{b.number}. [{KIND_NAMES.get(b.kind, b.kind)}] {b.text}" for b in blocks)
    parts.append("Page to translate:\n" + page)
    return "\n\n".join(parts)


def parse_translations(
    response: str, numbers: set[int], notes: dict[int, str] | None = None
) -> dict[int, str]:
    """Prevodi po broju bloka; napomene prevodioca (ako ih ima) idu u `notes`."""
    try:
        items = json.loads(response).get("translations", [])
    except (ValueError, AttributeError):
        return {}
    result: dict[int, str] = {}
    for item in items if isinstance(items, list) else []:
        try:
            number = int(item.get("number"))
        except (AttributeError, TypeError, ValueError):
            continue
        text = serbian_forms(to_latin(lettering(BLOCK_MARKER.sub("", str(item.get("text", ""))))))
        if number in numbers and text and number not in result:
            result[number] = text
            note = " ".join(str(item.get("note") or "").split())
            if notes is not None and note:
                notes[number] = to_latin(note)
    return result


EMPHASIS_SPAN = re.compile(r"\*[^*\s][^*]*\*")


def emphasis_count(text: str) -> int:
    """Broj naglašenih delova (`*…*`)."""
    return len(EMPHASIS_SPAN.findall(text))


def keep_emphasis(source: str, translation: str) -> str:
    """Oznake naglaska ostaju samo ako ih prevod ima koliko i original; inače se skidaju, pa lektura
    javlja da naglasak nije prenet."""
    if emphasis_count(translation) == emphasis_count(source) and translation.count("*") % 2 == 0:
        return translation
    return " ".join(translation.replace("*", "").split())


def is_too_long(source: str, translation: str) -> bool:
    source, translation = source.replace("*", ""), translation.replace("*", "")
    return len(translation) > MAX_LENGTH_RATIO * max(len(source), MIN_LENGTH)


def _generate(model: str, prompt: str) -> str:
    result = llm.translation_client(model).generate(
        prompt, model, MAX_TOKENS, temperature=TEMPERATURE, format=SCHEMA
    )
    return result.response


def translate_blocks(
    model: str,
    blocks: list[SourceBlock],
    glossary: Pairs,
    context: Pairs,
    examples: Pairs,
    style: Style | None = None,
    notes: dict[int, str] | None = None,
) -> dict[int, str]:
    """Cela stranica jednim zahtevom; blok koji model preskoči prevodi se posebno.

    Napomene prevodioca (igra reči, kulturna referenca) se upisuju u `notes`, ako je dat.
    """
    page_glossary = relevant_glossary(glossary, " ".join(block.text for block in blocks))
    prompt = build_prompt(blocks, page_glossary, context, examples, style)
    numbers = {b.number for b in blocks}
    translations = parse_translations(_generate(model, prompt), numbers, notes)
    for block in blocks:
        # dugačak blok uz pun prompt ume da ostane prazan, pa je drugi pokušaj bez primera
        for extra in ((context, examples), ([], [])):
            if block.number in translations:
                break
            single = build_prompt([block], page_glossary, *extra, style)
            translations.update(parse_translations(_generate(model, single), {block.number}, notes))
    return {
        block.number: keep_emphasis(block.text, translations[block.number])
        for block in blocks
        if block.number in translations
    }


def shorten(
    model: str, block: SourceBlock, current: str, glossary: Pairs, style: Style | None = None
) -> str | None:
    prompt = build_prompt([block], relevant_glossary(glossary, block.text), [], [], style) + (
        f"\n\nThe current translation is too long for the balloon: {current}\n"
        f"Give a shorter translation with the same meaning, "
        f"at most {len(block.text)} characters."
    )
    text = parse_translations(_generate(model, prompt), {block.number}).get(block.number)
    return keep_emphasis(block.text, text) if text else None
