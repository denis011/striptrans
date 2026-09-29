import json
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import LlamaDep, SessionDep, SettingsDep
from app.models import Job, Page, TextBlock, TranslationStyle
from app.routers.pages import get_page
from app.schemas import (
    AiPatchRequest,
    AiPromptOut,
    BlockIds,
    BlockIn,
    BlockOut,
    BlockPatch,
    JobOut,
    OcrRequest,
    PatchOut,
    PreviewOut,
    PreviewRequest,
    ProcessRequest,
    TranslateRequest,
)
from app.services import ai_patch, emphasis, history, llm, title
from app.services.glossary_suggest import flatten
from app.services.llm_base import LlmError
from app.services.ocr import read_block
from app.services.page_processing import PageImage, page_panels
from app.services.page_translation import (
    TranslationFailed,
    preview_block,
    remember,
    translate_block,
)
from app.services.panels import order_by_panels
from app.services.translation import is_too_long

router = APIRouter(prefix="/api", tags=["blocks"])

DUPLICATE_OFFSET = 20
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
TITLE_FIELDS = ("kind", "text", "x", "y", "width", "height")  # izmena traži novo isecanje slova


def get_block(session: Session, block_id: int) -> TextBlock:
    block = session.get(TextBlock, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "blok ne postoji")
    return block


def page_blocks(session: Session, page_id: int) -> list[TextBlock]:
    query = select(TextBlock).where(TextBlock.page_id == page_id)
    return list(session.scalars(query.order_by(TextBlock.position, TextBlock.id)))


def _renumber(blocks: list[TextBlock]) -> list[TextBlock]:
    for position, block in enumerate(blocks, start=1):
        block.position = position
    return blocks


def _fit_to_page(block: TextBlock, page: Page) -> None:
    block.x = min(max(block.x, 0), page.width - 1)
    block.y = min(max(block.y, 0), page.height - 1)
    block.width = max(1, min(block.width, page.width - block.x))
    block.height = max(1, min(block.height, page.height - block.y))


@router.get("/pages/{page_id}/blocks")
def list_blocks(page_id: int, session: SessionDep) -> list[BlockOut]:
    get_page(session, page_id)
    return page_blocks(session, page_id)


@router.post("/pages/{page_id}/blocks", status_code=status.HTTP_201_CREATED)
def create_block(page_id: int, data: BlockIn, session: SessionDep) -> BlockOut:
    page = get_page(session, page_id)
    history.record(session, page, "nov blok")
    position = len(page_blocks(session, page_id)) + 1
    block = TextBlock(page_id=page_id, position=position, source="manual", **data.model_dump())
    _fit_to_page(block, page)
    session.add(block)
    session.commit()
    return block


def _continuation(session: Session, block: TextBlock, target_id: int | None) -> int | None:
    """Nastavak mora biti drugi blok iste stranice, bez drugog prethodnika i bez kruga."""
    if target_id is None:
        return None
    target = session.get(TextBlock, target_id)
    if target is None or target.page_id != block.page_id or target.id == block.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "nastavak mora biti blok iste stranice"
        )
    other = session.scalar(
        select(TextBlock).where(TextBlock.continues_id == target.id, TextBlock.id != block.id)
    )
    if other is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"blok {target.position} je već nastavak bloka {other.position}",
        )
    step, seen = target, set()
    while step is not None and step.id not in seen:
        if step.id == block.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "veza bi napravila krug")
        seen.add(step.id)
        step = session.get(TextBlock, step.continues_id) if step.continues_id else None
    return target.id


@router.patch("/blocks/{block_id}")
def update_block(
    block_id: int, data: BlockPatch, session: SessionDep, settings: SettingsDep
) -> BlockOut:
    block = get_block(session, block_id)
    history.record(session, block.page, "izmena bloka")
    letter_fonts = (block.style or {}).get("letter_fonts") or {}
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "style" in data.model_fields_set:  # null je dozvoljen: vraća automatsko slaganje
        changes["style"] = data.style.model_dump() if data.style else None
    if "continues_id" in data.model_fields_set:
        changes["continues_id"] = _continuation(session, block, data.continues_id)
    if "translation" in changes:
        changes["translation"] = changes["translation"].upper()
        # obrisan prevod nije ručna izmena: blok je ponovo „bez prevoda" (prevod ga popunjava)
        empty = not changes["translation"].strip()
        changes.setdefault("translation_status", "none" if empty else "edited")
        if empty:
            changes["translation_note"] = None
        block.translation_too_long = is_too_long(flatten(block.text), changes["translation"])
    for field, value in changes.items():
        setattr(block, field, value)
    if changes.get("translation_status") == "approved":
        remember(session, block)
    _fit_to_page(block, block.page)
    data_dir = Path(settings.data_dir)
    fonts_changed = ((block.style or {}).get("letter_fonts") or {}) != letter_fonts
    if block.kind == "title" and (
        block.title is None or fonts_changed or any(f in changes for f in TITLE_FIELDS)
    ):
        title.refresh(block, data_dir)
    elif block.kind != "title" and block.title is not None:
        shutil.rmtree(
            title.title_dir(data_dir, block.page.project_id, block.id), ignore_errors=True
        )
        block.title = None
    session.commit()
    return block


@router.post("/blocks/{block_id}/title")
def cut_title(block_id: int, session: SessionDep, settings: SettingsDep) -> BlockOut:
    """Ponovo iseci slova naslova iz originala (npr. posle ispravke teksta ili okvira)."""
    block = get_block(session, block_id)
    if block.kind != "title":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "blok nije naslov")
    history.record(session, block.page, "sečenje slova")
    title.refresh(block, Path(settings.data_dir))
    session.commit()
    return block


@router.post("/blocks/{block_id}/glyphs")
async def save_glyph(
    block_id: int,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    char: Annotated[str, Form()],
    baseline: Annotated[float, Form()],
    parts: Annotated[str, Form()] = "[]",
    key: Annotated[str | None, Form()] = None,
    fill: Annotated[UploadFile | None, File()] = None,
) -> BlockOut:
    """Slovo naslova sastavljeno od delova slova originala (6b); `key` zamenjuje postojeće."""
    block = get_block(session, block_id)
    history.record(session, block.page, "novo slovo" if key is None else "izmena slova")
    try:
        definition = json.loads(parts)
        filled = await fill.read() if fill is not None else None
        title.save_custom(
            block,
            Path(settings.data_dir),
            await file.read(),
            char,
            baseline,
            definition,
            key,
            filled,
        )
    except (ValueError, title.GlyphError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    session.commit()
    return block


@router.delete("/blocks/{block_id}/glyphs/{key}")
def delete_glyph(block_id: int, key: str, session: SessionDep, settings: SettingsDep) -> BlockOut:
    block = get_block(session, block_id)
    history.record(session, block.page, "brisanje slova")
    try:
        title.remove_custom(block, Path(settings.data_dir), key)
    except title.GlyphError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    session.commit()
    return block


@router.get("/blocks/{block_id}/glyphs/{key}.png")
def title_glyph(
    block_id: int, key: str, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    path = title.glyph_file(Path(settings.data_dir), get_block(session, block_id), key)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "slovo ne postoji")
    return FileResponse(path, media_type="image/png", headers=IMMUTABLE)


@router.delete("/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_block(block_id: int, session: SessionDep, settings: SettingsDep) -> Response:
    block = get_block(session, block_id)
    history.record(session, block.page, "brisanje bloka")
    # slike slova ostaju: „Poništi" vraća blok sa istim brojem, pa i sa svojim slovima
    session.delete(block)
    session.flush()
    _renumber(page_blocks(session, block.page_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/pages/{page_id}/blocks/order")
def reorder_blocks(page_id: int, data: BlockIds, session: SessionDep) -> list[BlockOut]:
    page = get_page(session, page_id)
    by_id = {block.id: block for block in page_blocks(session, page_id)}
    if sorted(data.block_ids) != sorted(by_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "lista se ne poklapa sa blokovima stranice"
        )
    history.record(session, page, "redosled blokova")
    blocks = _renumber([by_id[block_id] for block_id in data.block_ids])
    session.commit()
    return blocks


@router.post("/pages/{page_id}/blocks/merge")
def merge_blocks(page_id: int, data: BlockIds, session: SessionDep) -> list[BlockOut]:
    """Spoji izabrane blokove u prvi po redosledu: zajednički okvir, tekstovi redom."""
    page = get_page(session, page_id)
    wanted = set(data.block_ids)
    selected = [block for block in page_blocks(session, page_id) if block.id in wanted]
    if len(selected) < 2 or len(selected) != len(wanted):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "izaberi bar dva bloka ove stranice")
    history.record(session, page, "spajanje blokova")
    merged, rest = selected[0], selected[1:]
    right = max(block.x + block.width for block in selected)
    bottom = max(block.y + block.height for block in selected)
    merged.x = min(block.x for block in selected)
    merged.y = min(block.y for block in selected)
    merged.width = right - merged.x
    merged.height = bottom - merged.y
    merged.text = "\n".join(block.text for block in selected if block.text)
    merged.ocr_text = "\n".join(block.ocr_text for block in selected if block.ocr_text) or None
    merged.needs_review = any(block.needs_review for block in selected)
    merged.bubble_polygon = None
    for block in rest:
        session.delete(block)
    session.flush()
    blocks = _renumber(page_blocks(session, page_id))
    session.commit()
    return blocks


@router.post("/blocks/{block_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_block(block_id: int, session: SessionDep) -> BlockOut:
    """Kopija bloka odmah iza originala, malo pomerena; služi za ručnu podelu bloka."""
    block = get_block(session, block_id)
    history.record(session, block.page, "dupliranje bloka")
    for other in page_blocks(session, block.page_id):
        if other.position > block.position:
            other.position += 1
    copy = TextBlock(
        page_id=block.page_id,
        position=block.position + 1,
        kind=block.kind,
        x=block.x + DUPLICATE_OFFSET,
        y=block.y + DUPLICATE_OFFSET,
        width=block.width,
        height=block.height,
        text=block.text,
        ocr_text=block.ocr_text,
        source="manual",
        needs_review=block.needs_review,
    )
    _fit_to_page(copy, block.page)
    session.add(copy)
    session.commit()
    return copy


@router.post("/pages/{page_id}/blocks/auto-order")
def auto_order_blocks(page_id: int, session: SessionDep, settings: SettingsDep) -> list[BlockOut]:
    page = get_page(session, page_id)
    history.record(session, page, "automatski redosled")
    blocks = page_blocks(session, page_id)
    boxes = [(b.x, b.y, b.width, b.height) for b in blocks]
    order = order_by_panels(boxes, page_panels(page, settings))
    ordered = _renumber([blocks[index] for index in order])
    session.commit()
    return ordered


@router.post("/blocks/{block_id}/ocr")
def ocr_block(
    block_id: int,
    session: SessionDep,
    llama: LlamaDep,
    settings: SettingsDep,
    data: OcrRequest | None = None,
) -> BlockOut:
    """Pročitaj tekst bloka vision modelom; pročitani tekst zamenjuje tekst bloka."""
    block = get_block(session, block_id)
    history.record(session, block.page, "čitanje bloka")
    model = (data.model if data else None) or settings.ocr_model
    image_path = Path(settings.data_dir, block.page.image_path)
    try:
        language = block.page.project.series.source_lang
        result = read_block(llama, image_path, block, model, settings.ocr_max_tokens, language)
    except LlmError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    block.ocr_text = result.text
    block.text = result.text
    block.ocr_model = model
    block.needs_review = result.needs_review
    if settings.emphasis_detection:
        original = PageImage(image_path)
        emphasis.apply(block, original.image, original.gray)
    session.commit()
    return block


@router.get("/ocr/models")
def ocr_models(llama: LlamaDep, settings: SettingsDep) -> dict:
    """Model koji llama-server drži (jedan)."""
    try:
        models = llama.models()
    except LlmError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return {"default_model": settings.ocr_model, "models": models}


@router.post("/pages/{page_id}/process", status_code=status.HTTP_202_ACCEPTED)
def process_page_request(
    page_id: int, session: SessionDep, settings: SettingsDep, data: ProcessRequest | None = None
) -> JobOut:
    """Automatska obrada stranice u pozadini; postojeći blokovi stranice se zamenjuju."""
    page = get_page(session, page_id)
    model = (data.model if data else None) or settings.ocr_model
    job = Job(
        type="process_page",
        project_id=page.project_id,
        payload={"page_id": page_id, "model": model},
    )
    session.add(job)
    session.commit()
    return job


@router.post("/blocks/{block_id}/translate")
def translate_block_request(
    block_id: int,
    session: SessionDep,
    settings: SettingsDep,
    data: TranslateRequest | None = None,
) -> BlockOut:
    """Prevod jednog bloka ili, uz `shorter`, kraća verzija postojećeg prevoda."""
    block = get_block(session, block_id)
    if not block.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "blok nema tekst za prevod")
    history.record(session, block.page, "prevod bloka")
    model = (data.model if data else None) or settings.translation_model
    try:
        return translate_block(session, block, model, shorter=bool(data and data.shorter))
    except (LlmError, TranslationFailed) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.get("/blocks/{block_id}/ai-prompt")
def block_ai_prompt(block_id: int, session: SessionDep) -> AiPromptOut:
    """Isto uputstvo koje ide modelu za slike, za ručni rad u AI aplikaciji (pretplata)."""
    block = get_block(session, block_id)
    if not block.translation.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "blok nema prevod")
    kind = block.kind if block.kind in ai_patch.AI_KINDS else "other"
    return AiPromptOut(prompt=ai_patch.build_prompt(block, kind))


@router.post("/blocks/{block_id}/translate/preview")
def preview_block_translation(
    block_id: int, session: SessionDep, settings: SettingsDep, data: PreviewRequest | None = None
) -> PreviewOut:
    """Probni prevod bloka sa izabranim (ili aktivnim) stilom; ništa se ne upisuje."""
    block = get_block(session, block_id)
    if not block.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "blok nema tekst za prevod")
    model = (data.model if data else None) or settings.translation_model
    if data and data.style_id and session.get(TranslationStyle, data.style_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stil ne postoji")
    try:
        text, note = preview_block(session, block, model, data.style_id if data else None)
    except (LlmError, TranslationFailed) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return PreviewOut(translation=text, note=note)


@router.post("/pages/{page_id}/translate", status_code=status.HTTP_202_ACCEPTED)
def translate_page_request(
    page_id: int, session: SessionDep, settings: SettingsDep, data: OcrRequest | None = None
) -> JobOut:
    page = get_page(session, page_id)
    model = (data.model if data else None) or settings.translation_model
    job = Job(
        type="translate_page",
        project_id=page.project_id,
        payload={"page_id": page_id, "model": model},
    )
    session.add(job)
    session.commit()
    return job


@router.get("/translation/models")
def translation_models(settings: SettingsDep) -> dict:
    """Modeli za prevod sa OpenRouter-a; bez ključa u `.env` prevod ne radi."""
    remote = llm.remote_models(settings)
    if not remote:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "OPENROUTER_API_KEY nije podešen (vidi .env)"
        )
    return {"default_model": settings.translation_model, "models": remote}


@router.post("/blocks/{block_id}/ai-patch", status_code=status.HTTP_202_ACCEPTED)
def ai_patch_request(
    block_id: int, session: SessionDep, settings: SettingsDep, data: AiPatchRequest | None = None
) -> JobOut:
    """AI prepravka natpisa: posao u redu pravi predlog slike (plaća se po pozivu)."""
    block = get_block(session, block_id)
    if block.kind not in ai_patch.AI_KINDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "AI prepravka je za naslove, natpise i onomatopeje"
        )
    if not block.translation.strip() or not block.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "blok nema originalni tekst ili prevod")
    if not settings.openrouter_api_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OpenRouter ključ nije podešen")
    page = block.page
    job = Job(
        type="ai_patch",
        project_id=page.project_id,
        payload={"block_id": block_id, "quality": data.quality if data else "quality"},
    )
    session.add(job)
    session.commit()
    return job


@router.get("/blocks/{block_id}/ai-proposals")
def ai_proposals(block_id: int, session: SessionDep) -> list[dict]:
    """Već plaćeni predlozi za blok, najnoviji prvi: mogu se ponovo prihvatiti bez novog poziva."""
    get_block(session, block_id)
    jobs = session.scalars(
        select(Job).where(Job.type == "ai_patch", Job.status == "done").order_by(Job.id.desc())
    ).all()
    return [
        {
            "job_id": job.id,
            "model": job.result.get("model"),
            "cost": job.result.get("cost"),
            "created_at": job.created_at,
        }
        for job in jobs
        if job.result and job.result.get("block_id") == block_id
    ]


def ai_result(session: Session, job_id: int) -> tuple[Job, dict]:
    job = session.get(Job, job_id)
    if job is None or job.type != "ai_patch" or job.status != "done" or not job.result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "predlog ne postoji")
    return job, job.result


@router.get("/jobs/{job_id}/ai-image")
def ai_patch_image(job_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    _, result = ai_result(session, job_id)
    return FileResponse(Path(settings.data_dir, result["image"]), media_type="image/png")


@router.post("/jobs/{job_id}/ai-accept", status_code=status.HTTP_201_CREATED)
def ai_patch_accept(job_id: int, session: SessionDep, settings: SettingsDep) -> PatchOut:
    """Prihvaćen predlog postaje zakrpa preko okvira bloka (poništava se sa Ctrl+Z)."""
    _, result = ai_result(session, job_id)
    block = get_block(session, result["block_id"])
    page = block.page
    history.record(session, page, "AI prepravka")
    patch = ai_patch.accept(session, Path(settings.data_dir), page, block, result)
    session.commit()
    return patch
