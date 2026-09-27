"""Automatska obrada stranice: detekcija blokova, paneli, redosled čitanja i OCR."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy import delete
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import ObjectDeletedError

from app.config import Settings
from app.models import Page, TextBlock
from app.services import emphasis, history
from app.services.detector import DetectedBlock, detect, text_blocks
from app.services.geometry import Box, rect_polygon
from app.services.llamaserver import LlamaServerClient
from app.services.llm_base import LlmError
from app.services.ocr import not_a_sound, read_block
from app.services.panels import detect_panels, order_by_panels
from app.services.sfx import sfx_candidates

# poziva se posle svakog pročitanog bloka sa (pročitano, ukupno); može da prekine obradu izuzetkom
BlockCallback = Callable[[int, int], None]


@dataclass
class PageResult:
    blocks: int = 0
    needs_review: int = 0
    skipped: bool = False


def detector_path(settings: Settings) -> Path:
    return Path(settings.models_dir, "comic-text-and-bubble-detector", settings.detector_model)


def sfx_model_path(settings: Settings) -> Path:
    return Path(settings.models_dir, "comic-text-detector", "comic-text-detector.onnx")


def page_panels(page: Page, settings: Settings) -> list[Box]:
    """Paneli stranice; računaju se pri prvom zahtevu i pamte na stranici."""
    if page.panels is None:
        with Image.open(Path(settings.data_dir, page.image_path)) as image:
            page.panels = [list(panel) for panel in detect_panels(np.asarray(image.convert("L")))]
    return [tuple(panel) for panel in page.panels]


def detect_blocks(session: Session, settings: Settings, page: Page) -> list[TextBlock]:
    """Zameni blokove stranice detektovanim blokovima, u redosledu čitanja."""
    session.execute(delete(TextBlock).where(TextBlock.page_id == page.id))
    session.expire(page, ["blocks"])
    with Image.open(Path(settings.data_dir, page.image_path)) as image:
        detections = detect(image, detector_path(settings))
        detected = text_blocks(detections)
        if settings.sfx_detection:
            known = [detection.box for detection in detections]
            candidates = sfx_candidates(image, known, sfx_model_path(settings))
            detected += [DetectedBlock("sfx", box, None, None) for box in candidates]
        page.panels = [list(panel) for panel in detect_panels(np.asarray(image.convert("L")))]
    order = order_by_panels([item.box for item in detected], page_panels(page, settings))
    blocks = []
    for position, index in enumerate(order, start=1):
        item = detected[index]
        x, y, width, height = item.box
        block = TextBlock(
            page_id=page.id,
            position=position,
            kind=item.kind,
            x=x,
            y=y,
            width=width,
            height=height,
            bubble_polygon=rect_polygon(item.bubble) if item.bubble else None,
            confidence=item.score,
            source="auto",
            text="",
            needs_review=item.kind == "sfx",  # predlog iz maske: korisnik proverava okvir
        )
        session.add(block)
        blocks.append(block)
    session.flush()
    return blocks


def _still_there(session: Session, block: TextBlock) -> bool:
    """Da li blok još postoji: obrada traje, a korisnik u editoru može da ga obriše ili poništi."""
    try:
        session.refresh(block)
    except (ObjectDeletedError, InvalidRequestError):
        return False
    return True


def unread(block: TextBlock) -> bool:
    """Automatski blok koji OCR nikad nije pročitao: obrada je prekinuta posle detekcije."""
    return block.source == "auto" and block.ocr_model is None


class PageImage:
    """Original stranice za naglasak: slika i siva verzija (oblik oblačića)."""

    def __init__(self, path: Path):
        with Image.open(path) as image:
            self.image = image.convert("L")
        self.gray = np.array(self.image)  # menja se privremeno pri merenju oblika oblačića


def process_page(
    session: Session,
    settings: Settings,
    client: LlamaServerClient,
    page: Page,
    model: str,
    replace: bool = True,
    on_block: BlockCallback | None = None,
) -> PageResult:
    """Detekcija i OCR stranice; preskače označene i (bez `replace`) već obrađene stranice.

    Bez `replace` stranica sa nepročitanim blokovima nije obrađena: čitaju se samo ti blokovi, bez
    nove detekcije, pa ručne ispravke ostaju.
    """
    if page.skip:
        return PageResult(skipped=True)
    if page.blocks and not replace:
        blocks = [block for block in page.blocks if unread(block)]
        if not blocks:
            return PageResult(skipped=True)
        history.record(session, page, "čitanje nepročitanih blokova")
    else:
        history.record(session, page, "obrada stranice")
        blocks = detect_blocks(session, settings, page)
    session.commit()
    image_path = Path(settings.data_dir, page.image_path)
    language = page.project.series.source_lang
    result = PageResult(blocks=len(blocks))
    original: PageImage | None = None  # učitava se tek za prvi pročitan blok
    for done, block in enumerate(blocks, start=1):
        if not _still_there(session, block):
            # korisnik je blok obrisao (ili vratio stanje pre obrade) dok je OCR radio: preskoči ga
            if on_block:
                on_block(done, len(blocks))
            continue
        try:
            ocr = read_block(client, image_path, block, model, settings.ocr_max_tokens, language)
        except LlmError as exc:
            if not exc.model_failed:
                raise  # llama-server ne radi: posao staje i nastavlja se kasnije
            # model se na ovom bloku zavrteo u krug ili pao: blok ostaje prazan, za proveru
            block.ocr_model = model
            block.needs_review = True
            result.needs_review += 1
            session.commit()
            if on_block:
                on_block(done, len(blocks))
            continue
        block.ocr_text = block.text = ocr.text
        if block.kind == "sfx" and not_a_sound(ocr.text):
            block.kind = "other"  # natpis ili naslov, ne onomatopeja
        block.ocr_model = model
        block.needs_review = block.needs_review or ocr.needs_review
        if settings.emphasis_detection:
            original = original or PageImage(image_path)
            emphasis.apply(block, original.image, original.gray)
        result.needs_review += block.needs_review
        session.commit()
        if on_block:
            on_block(done, len(blocks))
    return result
