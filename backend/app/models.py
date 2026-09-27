from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

PAGE_KINDS = ("original", "reference")
BLOCK_KINDS = ("speech", "thought", "caption", "sfx", "other", "title")
GLOSSARY_KINDS = ("name", "place", "phrase")  # onomatopeje imaju svoj glosar


def utcnow() -> datetime:
    """Naivno UTC vreme; SQLite ne čuva vremensku zonu."""
    return datetime.now(UTC).replace(tzinfo=None)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    source_lang: Mapped[str] = mapped_column(String(10), default="it")
    target_lang: Mapped[str] = mapped_column(String(10), default="sr")
    # ključ fonta (ugrađeni, npr. „comic-neue-bold", ili „user-5"); None = podrazumevani
    dialogue_font: Mapped[str | None] = mapped_column(String(100))
    sfx_font: Mapped[str | None] = mapped_column(String(100))
    # naracija ukošena (kao u srpskim izdanjima); naglašen tekst je uvek podebljan i ukošen
    caption_italic: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GlossaryEntry(Base):
    __tablename__ = "glossary_entries"
    __table_args__ = (UniqueConstraint("series_id", "source", "target", name="uq_glossary_entry"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(200))  # italijanski izraz, velikim slovima
    target: Mapped[str] = mapped_column(String(200))  # srpski prevod, velikim slovima
    kind: Mapped[str] = mapped_column(String(20), default="phrase")
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="approved")  # suggested | approved
    origin: Mapped[str] = mapped_column(String(20), default="manual")  # manual | reference
    occurrences: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Font(Base):
    """Korisnički font (TTF/OTF) u /data/fonts; ugrađeni fontovi nisu u bazi."""

    __tablename__ = "fonts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(500))  # relativno u odnosu na data_dir
    kind: Mapped[str] = mapped_column(String(20), default="dialogue")  # dialogue | sfx
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DictionaryWord(Base):
    """Reč koju je korisnik potvrdio u lekturi (imena i uzvici kojih nema u hunspell rečniku)."""

    __tablename__ = "dictionary_words"
    __table_args__ = (UniqueConstraint("series_id", "word", name="uq_dictionary_word"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    word: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"))
    issue_number: Mapped[str | None] = mapped_column(String(20))
    original_title: Mapped[str | None] = mapped_column(String(200))
    translated_title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    series: Mapped[Series] = relationship()
    pages: Mapped[list["Page"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="[Page.kind, Page.position]",
    )


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (Index("ix_pages_project_kind_position", "project_id", "kind", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    position: Mapped[int]
    # redni broj pri uvozu; služi za vraćanje izvornog redosleda
    import_order: Mapped[int]
    source_name: Mapped[str] = mapped_column(String(500))
    width: Mapped[int]
    height: Mapped[int]
    image_path: Mapped[str] = mapped_column(String(500))
    thumbnail_path: Mapped[str] = mapped_column(String(500))
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    skip: Mapped[bool] = mapped_column(default=False)
    ocr_reviewed: Mapped[bool] = mapped_column(default=False)
    translation_reviewed: Mapped[bool] = mapped_column(default=False)
    # paneli (x, y, širina, visina) u redosledu čitanja; računaju se pri obradi
    panels: Mapped[list | None] = mapped_column(JSON)
    # očišćena slika (tekst u oblačićima prekriven) i maska prekrivenih piksela
    clean_path: Mapped[str | None] = mapped_column(String(500))
    mask_path: Mapped[str | None] = mapped_column(String(500))
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime)

    project: Mapped[Project] = relationship(back_populates="pages")
    blocks: Mapped[list["TextBlock"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="TextBlock.position"
    )


class TextBlock(Base):
    __tablename__ = "text_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]
    kind: Mapped[str] = mapped_column(String(20), default="speech")
    # okvir teksta u pikselima stranice
    x: Mapped[float]
    y: Mapped[float]
    width: Mapped[float]
    height: Mapped[float]
    bubble_polygon: Mapped[list | None] = mapped_column(JSON)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None]
    ocr_model: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20), default="manual")
    needs_review: Mapped[bool] = mapped_column(default=False)
    translation: Mapped[str] = mapped_column(Text, default="")
    translation_model: Mapped[str | None] = mapped_column(String(100))
    # none | draft (prevod modela) | edited (ispravio korisnik) | approved (lektorisano)
    translation_status: Mapped[str] = mapped_column(String(20), default="none")
    translation_too_long: Mapped[bool] = mapped_column(default=False)
    # ručne korekcije slaganja (veličina, pomeraj, rotacija...); None = sve automatski
    style: Mapped[dict | None] = mapped_column(JSON)
    # nagib originalne onomatopeje/natpisa (stepeni), procenjen pri čišćenju
    angle: Mapped[float | None]
    # podloga bloka posle čišćenja je tamna (naslov belim slovima na crnom): prevod se slaže svetlo
    dark_background: Mapped[bool | None]
    # naslov (Faza 6a): slova isečena iz originala i dopunjena, opis iz app.services.title.describe
    title: Mapped[dict | None] = mapped_column(JSON)
    # tekst se nastavlja u drugom bloku iste stranice (kolone uvodnika, prelomljen oblačić):
    # lanac se prevodi u jednom komadu
    continues_id: Mapped[int | None] = mapped_column(
        ForeignKey("text_blocks.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    page: Mapped[Page] = relationship(back_populates="blocks")


class Patch(Base):
    """Zakrpa slikom (Faza 6c): PNG napravljen van aplikacije, postavljen preko stranice."""

    __tablename__ = "patches"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]  # redosled crtanja; veći je iznad
    path: Mapped[str] = mapped_column(String(500))  # relativno u odnosu na data_dir
    x: Mapped[float]
    y: Mapped[float]
    width: Mapped[float]
    height: Mapped[float]
    rotation: Mapped[float] = mapped_column(default=0.0)
    opacity: Mapped[float] = mapped_column(default=1.0)
    above_text: Mapped[bool] = mapped_column(default=False)  # crta se i preko složenog prevoda
    # vidljivost piksela zakrpe (PNG „L" u veličini slike, 0 = obrisano četkicom);
    # None = cela vidljiva. Svaka izmena je nov fajl, pa „Poništi" samo vraća putanju.
    mask_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    page: Mapped["Page"] = relationship()


class PageHistory(Base):
    """Snimak blokova stranice za „Poništi" i „Ponovi"; dva niza (undo, redo) po stranici."""

    __tablename__ = "page_history"
    __table_args__ = (Index("ix_page_history_page_kind", "page_id", "kind", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # undo | redo
    position: Mapped[int]  # veći broj je noviji snimak
    action: Mapped[str] = mapped_column(String(60))  # naziv radnje, npr. „pomeranje bloka"
    blocks: Mapped[list] = mapped_column(JSON)
    # isečak očišćene slike i maske pre poteza četkicom: {"box": [x, y, w, h], "name": ...}
    patch: Mapped[dict | None] = mapped_column(JSON)
    patches: Mapped[list | None] = mapped_column(JSON)  # zakrpe stranice (Faza 6c)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SfxEntry(Base):
    """Glosar onomatopeja, zajednički za sve serijale; ključ su samo slova (WOAH! = WOAH)."""

    __tablename__ = "sfx_glossary"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(200), unique=True)
    target: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class TranslationMemory(Base):
    """Odobren prevod za tačno isti italijanski tekst u serijalu."""

    __tablename__ = "translation_memory"
    __table_args__ = (UniqueConstraint("series_id", "source", name="uq_translation_memory"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Export(Base):
    """Izvoz albuma: browser crta stranice, backend ih prima i pakuje (CBZ, PDF, ZIP)."""

    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[str] = mapped_column(String(10))  # cbz | pdf | zip
    image_format: Mapped[str] = mapped_column(String(10))  # jpeg | png
    quality: Mapped[int] = mapped_column(default=92)
    skipped: Mapped[str] = mapped_column(String(10), default="include")  # include | omit
    positions: Mapped[list] = mapped_column(JSON)  # stranice originala u albumu, redom
    status: Mapped[str] = mapped_column(
        String(20), default="uploading"
    )  # uploading|packing|done|failed
    received: Mapped[list] = mapped_column(JSON, default=list)  # primljene nacrtane stranice
    path: Mapped[str | None] = mapped_column(
        String(500)
    )  # gotov fajl, relativno u odnosu na data_dir
    size: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TranslationRating(Base):
    """Slepa ručna ocena jednog prevoda (kandidat = model/varijanta, skriven od ocenjivača)."""

    __tablename__ = "translation_ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    study: Mapped[str] = mapped_column(String(50), index=True)
    item: Mapped[int]  # redni broj bloka u uzorku
    page_position: Mapped[int]
    block_position: Mapped[int]
    source: Mapped[str] = mapped_column(Text)
    candidate: Mapped[str] = mapped_column(String(100))
    order: Mapped[int]  # nasumičan redosled kandidata u okviru bloka
    translation: Mapped[str] = mapped_column(Text)
    score: Mapped[int | None]
    rated_at: Mapped[datetime | None] = mapped_column(DateTime)
