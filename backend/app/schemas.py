from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

PageKind = Literal["original", "reference"]
BlockKind = Literal["speech", "thought", "caption", "sfx", "other", "title"]
GlossaryKind = Literal["name", "place", "phrase", "sfx"]
GlossaryStatus = Literal["suggested", "approved"]
TranslationStatus = Literal["none", "draft", "edited", "approved"]


class SeriesIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_lang: str = Field(default="it", max_length=10)
    target_lang: str = Field(default="sr", max_length=10)


class SeriesOut(SeriesIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dialogue_font: str | None = None
    sfx_font: str | None = None
    caption_italic: bool = False


class SeriesPatch(BaseModel):
    dialogue_font: str | None = Field(default=None, max_length=100)
    sfx_font: str | None = Field(default=None, max_length=100)
    caption_italic: bool | None = None  # naracija ukošena


class FontOut(BaseModel):
    key: str  # „comic-neue-bold" za ugrađene, „user-5" za korisničke
    name: str
    kind: Literal["dialogue", "sfx", "title"]  # title: osnova slova naslova (6b)
    builtin: bool
    url: str


class ProjectPatch(BaseModel):
    issue_number: str | None = Field(default=None, max_length=20)
    original_title: str | None = Field(default=None, max_length=200)
    translated_title: str | None = Field(default=None, max_length=200)


class ProjectIn(ProjectPatch):
    series_id: int


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: PageKind
    position: int
    import_order: int
    source_name: str
    width: int
    height: int
    skip: bool
    ocr_reviewed: bool
    translation_reviewed: bool
    cleaned_at: datetime | None = None


class PagePatch(BaseModel):
    skip: bool | None = None
    ocr_reviewed: bool | None = None
    translation_reviewed: bool | None = None


class MaskStroke(BaseModel):
    mode: Literal["add", "erase", "inpaint"]
    radius: float = Field(gt=0, le=200)
    points: list[tuple[float, float]] = Field(min_length=1, max_length=5000)


class MaskEdit(BaseModel):
    strokes: list[MaskStroke] = Field(min_length=1, max_length=100)


class PageOrder(BaseModel):
    kind: PageKind
    page_ids: list[int]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    project_id: int | None
    progress: int
    total: int
    cancel_requested: bool
    error: str | None
    result: dict | None
    created_at: datetime
    updated_at: datetime


class ActiveJobOut(JobOut):
    """Posao iz reda (čeka ili radi), sa nazivom projekta za pregled na strani Status."""

    project_title: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series: SeriesOut
    issue_number: str | None
    original_title: str | None
    translated_title: str | None
    created_at: datetime
    page_count: int
    reference_page_count: int
    cover_page_id: int | None


class ProjectProgress(BaseModel):
    """Stanje koraka obrade (strana projekta); preskočene stranice se ne broje."""

    pages: int = 0  # stranice originala koje se obrađuju
    skipped: list[int] = []  # pozicije preskočenih stranica
    with_blocks: int = 0  # stranice sa blokovima, svi automatski pročitani
    unread: int = 0  # automatski blokovi koje OCR nije pročitao (prekinuta obrada)
    # izvoz u toku: {stage: drawing|packing, done, total, stale}; stale: tab je verovatno zatvoren
    export_active: dict | None = None
    ai_calls: int = 0  # AI prepravke natpisa (predlozi, i odbačeni)
    ai_cost: float = 0  # njihov zbirni trošak ($)
    blocks: int = 0  # blokovi sa tekstom
    translation: dict[str, int] = {}  # none | draft | edited | approved
    proofread: int = 0  # lektorisane stranice
    cleaned: int = 0  # očišćene stranice
    exported_at: datetime | None = None  # poslednji uspešan izvoz albuma
    changed_at: datetime | None = (
        None  # poslednja izmena blokova ili čišćenja (izvoz stariji = zastareo)
    )


class ProjectDetail(ProjectOut):
    pages: list[PageOut]
    jobs: list[JobOut]
    progress: ProjectProgress = ProjectProgress()


class BlockIn(BaseModel):
    kind: BlockKind = "speech"
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    text: str = ""


class LetterStyle(BaseModel):
    """Ručna izmena jednog slova naslova."""

    key: str | None = Field(default=None, max_length=10)  # izabran primerak (g0, x3...)
    dx: float = Field(default=0, ge=-2, le=2)  # pomeraj u visinama slova
    dy: float = Field(default=0, ge=-2, le=2)
    rotation: float = Field(default=0, ge=-90, le=90)  # stepeni, oko sredine slova (naslov u luku)


HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class LetteringStyle(BaseModel):
    """Ručne korekcije složenog prevoda; vrednosti su odstupanja od automatskog slaganja."""

    scale: float = Field(default=1, ge=0.3, le=3)  # veličina slova u odnosu na automatsku
    dx: float = 0  # pomeraj u pikselima stranice
    dy: float = 0
    rotation: float = Field(default=0, ge=-180, le=180)
    align: Literal["center", "left", "right", "justify"] = "center"  # justify: obostrano
    line_spacing: float = Field(default=1, ge=0.5, le=2)  # prored u odnosu na original
    font: str | None = Field(default=None, max_length=100)  # drugi font samo za ovaj blok
    # naslov od slova originala: popuni širinu originala ili zadrži veličinu slova
    fit: Literal["fill", "original"] = "fill"
    letter_spacing: float = Field(default=0, ge=-0.5, le=1)  # dodatni razmak, u visinama slova
    letters: dict[str, LetterStyle] = Field(default_factory=dict)  # po rednom broju slova prevoda
    # naslov: font za slova kojih nema u originalu, po slovu (K → „Anton"); bez njega bira se sam
    letter_fonts: dict[str, str] = Field(default_factory=dict)
    opaque: bool | None = None  # naslov: ispuna slova pokriva crtež; None = kao original (šuplja)
    # boja slova i obruba (naslovna, kolor strane); None = automatski: crno, belo na tamnoj podlozi
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    outline_color: str | None = Field(default=None, pattern=HEX_COLOR)
    outline_width: float | None = Field(default=None, ge=0, le=0.5)  # u veličinama slova; 0 = bez
    # uredničke strane i impresum: tekst puni okvir bloka, veličina slova se bira slobodno
    fill_box: bool = False
    # „Naglašeno": ceo blok podebljan i ukošen (vika, psovka), kao u srpskim izdanjima; deo se
    # naglašava zvezdicama u prevodu (*LARI*)
    emphasis: bool = False


class BlockPatch(BaseModel):
    kind: BlockKind | None = None
    x: float | None = Field(default=None, ge=0)
    y: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    text: str | None = None
    needs_review: bool | None = None
    translation: str | None = None
    translation_status: TranslationStatus | None = None
    style: LetteringStyle | None = None  # null vraća automatsko slaganje


class BlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    page_id: int
    position: int
    kind: BlockKind
    x: float
    y: float
    width: float
    height: float
    bubble_polygon: list[list[float]] | None
    ocr_text: str | None
    text: str
    confidence: float | None
    ocr_model: str | None
    source: str
    needs_review: bool
    translation: str
    translation_model: str | None
    translation_status: TranslationStatus
    translation_too_long: bool
    style: LetteringStyle | None = None
    angle: float | None = None
    dark_background: bool | None = None
    title: dict | None = None


class PatchOut(BaseModel):
    """Zakrpa slikom preko stranice (Faza 6c)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    x: float
    y: float
    width: float
    height: float
    rotation: float
    opacity: float
    above_text: bool

    @computed_field
    @property
    def url(self) -> str:
        return f"/api/patches/{self.id}/image"


class PatchPatch(BaseModel):
    x: float | None = None
    y: float | None = None
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    rotation: float | None = None
    opacity: float | None = Field(default=None, ge=0, le=1)
    above_text: bool | None = None
    position: int | None = None


class HistoryOut(BaseModel):
    """Šta „Poništi" i „Ponovi" trenutno mogu; `null` znači da nema koraka."""

    undo: str | None = None
    redo: str | None = None


class HistoryStep(BaseModel):
    action: str | None = None  # naziv poništene (ili ponovljene) radnje
    undo: str | None = None
    redo: str | None = None
    blocks: list[BlockOut] = []


class OcrRequest(BaseModel):
    model: str | None = None


class AiPatchRequest(BaseModel):
    quality: Literal["quality", "cheap"] = "quality"  # kvalitetno (flash) ili jeftino (flash-lite)


class TranslateRequest(OcrRequest):
    shorter: bool = False


class ProcessRequest(OcrRequest):
    replace: bool = False


class BlockIds(BaseModel):
    block_ids: list[int] = Field(min_length=1)


class GlossaryIn(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    kind: GlossaryKind = "phrase"
    note: str | None = None


class GlossarySuggestRequest(BaseModel):
    project_id: int
    reference_project_id: int
    model: str | None = None


class GlossaryPatch(BaseModel):
    source: str | None = Field(default=None, min_length=1, max_length=200)
    target: str | None = Field(default=None, min_length=1, max_length=200)
    kind: GlossaryKind | None = None
    note: str | None = None
    status: GlossaryStatus | None = None


class GlossaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    source: str
    target: str
    kind: GlossaryKind
    note: str | None
    status: GlossaryStatus
    origin: str
    occurrences: int


class DictionaryIn(BaseModel):
    word: str = Field(min_length=1, max_length=100)


class DictionaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    word: str


class BlockReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    block_id: int
    position: int
    unknown: list[str]  # reči kojih nema u rečniku
    glossary_missing: list[str]  # srpski izrazi iz glosara koje prevod ne koristi
    non_serbian: list[str] = []  # hrvatske i ijekavske reči (TISUĆU, TKO, UVIJEK)
    too_long: bool
    emphasis_missing: bool = False  # naglašene reči originala (`*…*`) nisu prenete u prevod


class PageReviewOut(BaseModel):
    page_id: int
    reviewed: bool
    blocks: list[BlockReviewOut]


class RatingScore(BaseModel):
    score: int = Field(ge=1, le=5)


class RatingCandidate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order: int
    translation: str
    score: int | None


class RatingItem(BaseModel):
    item: int
    page_position: int
    block_position: int
    source: str
    candidates: list[RatingCandidate]


class RatingStudy(BaseModel):
    study: str
    total_items: int
    rated_items: int
    items: list[RatingItem]


class ExportIn(BaseModel):
    format: Literal["cbz", "pdf", "zip"] = "cbz"
    image_format: Literal["jpeg", "png"] = "jpeg"
    quality: int = Field(default=92, ge=50, le=100)
    skipped: Literal["include", "omit"] = "include"  # preskočene stranice ulaze neizmenjene
    first: int | None = Field(default=None, ge=1)
    last: int | None = Field(default=None, ge=1)


class ExportPage(BaseModel):
    position: int
    page_id: int
    render: bool  # false: preskočena stranica, backend uzima original


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    format: str
    image_format: str
    quality: int
    skipped: str
    positions: list[int]
    received: list[int]
    status: str
    size: int | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    pages: list[ExportPage] = []


class PageReadiness(BaseModel):
    position: int
    page_id: int
    skip: bool
    cleaned: bool
    reviewed: bool
    blocks: int
    untranslated: int


class PrepareRequest(BaseModel):
    ocr_model: str | None = None
    translation_model: str | None = None
