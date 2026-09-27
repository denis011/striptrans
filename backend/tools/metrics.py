"""Metrike benchmarka: normalizacija teksta, CER, uparivanje okvira i redosled čitanja."""

import re
from collections import Counter

from app.services.geometry import (  # noqa: F401  (koriste ih benchmark i testovi)
    match_boxes,
    overlap,
)
from app.services.review import uses_glossary_term  # noqa: F401  (koristi ga benchmark)
from app.services.spellcheck import non_serbian_words  # noqa: F401  (koristi ga benchmark)

MAIN_KINDS = ("speech", "thought", "caption")
# „È", „E'" i „E`" su u letteringu isto slovo
TRANSLATION = str.maketrans(
    {
        "À": "A'", "Á": "A'", "È": "E'", "É": "E'", "Ì": "I'", "Í": "I'",
        "Ò": "O'", "Ó": "O'", "Ù": "U'", "Ú": "U'",
        "`": "'", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...",
    }
)  # fmt: skip


def group(kind: str) -> str:
    return "main" if kind in MAIN_KINDS else ("sfx" if kind == "sfx" else "other")


def normalize_text(text: str) -> str:
    """Tekst za poređenje: velika slova, spojene rastavljene reči, bez prelaza redova."""
    text = text.upper().translate(TRANSLATION)
    text = re.sub(r"-[ \t]*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+(?=[!?.,;:])", "", text)
    return text.strip()


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b))
            )
        previous = current
    return previous[-1]


def order_is_correct(matches: dict[int, int], considered: set[int]) -> bool:
    """Predviđeni blokovi su u redosledu čitanja; uparen zlatni redosled mora da raste."""
    sequence = [gold for _, gold in sorted(matches.items()) if gold in considered]
    return sequence == sorted(sequence)


def chrf(hypotheses: list[str], references: list[str], order: int = 6, beta: float = 2.0) -> float:
    """Korpusni chrF (Popović 2015): F-skor znakovnih n-grama 1..6 bez razmaka, 0–100."""
    matches, hypothesis_total, reference_total = [0] * order, [0] * order, [0] * order
    for hypothesis, reference in zip(hypotheses, references, strict=True):
        hyp, ref = hypothesis.replace(" ", ""), reference.replace(" ", "")
        for n in range(1, order + 1):
            hyp_grams = Counter(hyp[i : i + n] for i in range(len(hyp) - n + 1))
            ref_grams = Counter(ref[i : i + n] for i in range(len(ref) - n + 1))
            matches[n - 1] += sum((hyp_grams & ref_grams).values())
            hypothesis_total[n - 1] += sum(hyp_grams.values())
            reference_total[n - 1] += sum(ref_grams.values())
    precisions = [m / t for m, t in zip(matches, hypothesis_total, strict=True) if t]
    recalls = [m / t for m, t in zip(matches, reference_total, strict=True) if t]
    if not precisions or not recalls:
        return 0.0
    precision, recall = sum(precisions) / len(precisions), sum(recalls) / len(recalls)
    if precision + recall == 0:
        return 0.0
    return 100 * (1 + beta**2) * precision * recall / (beta**2 * precision + recall)
