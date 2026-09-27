"""Uvoz stranica: prepoznavanje formata po sadržaju, raspakivanje, sortiranje i priprema slika."""

import io
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import libarchive
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_FILES = 2000
MAX_TOTAL_BYTES = 1024**3
MAX_IMAGE_PIXELS = 120_000_000
PDF_DPI = 300
THUMBNAIL_WIDTH = 240
BROWSER_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
PNG_MODES = {"1", "L", "LA", "P", "RGB", "RGBA", "I;16"}
IGNORED_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}


class ImportFailed(Exception):
    """Greška uvoza sa porukom namenjenom korisniku."""


@dataclass
class PreparedPage:
    source_name: str
    data: bytes
    extension: str
    width: int
    height: int
    thumbnail: bytes


def natural_key(name: str) -> list[str | int]:
    parts = re.split(r"([0-9]+)", name.lower())
    return [int(part) if i % 2 else part for i, part in enumerate(parts)]


def is_ignored(path: str) -> bool:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    name = parts[-1] if parts else ""
    return (
        "__MACOSX" in parts
        or any(part.startswith(".") for part in parts)
        or name.lower() in IGNORED_NAMES
        or name.endswith(":Zone.Identifier")
    )


class _Budget:
    def __init__(self) -> None:
        self.files = 0
        self.bytes = 0

    def take(self, size: int) -> None:
        self.files += 1
        self.bytes += size
        if self.files > MAX_FILES:
            raise ImportFailed(f"previše fajlova (najviše {MAX_FILES})")
        if self.bytes > MAX_TOTAL_BYTES:
            raise ImportFailed(f"uvoz je prevelik (najviše {MAX_TOTAL_BYTES // 1024**2} MB)")


def detect_format(path: Path) -> str:
    """Vraća 'pdf', 'image' ili 'archive' na osnovu sadržaja fajla."""
    with path.open("rb") as file:
        if file.read(5) == b"%PDF-":
            return "pdf"
    try:
        with Image.open(path):
            return "image"
    except UnidentifiedImageError:
        pass
    except Image.DecompressionBombError as exc:
        raise ImportFailed("slika je prevelika") from exc
    try:
        with libarchive.file_reader(str(path)) as archive:
            next(iter(archive), None)
        return "archive"
    except libarchive.ArchiveError:
        raise ImportFailed("nepodržan format fajla") from None


def _iter_archive(path: Path) -> Iterator[tuple[str, bytes]]:
    try:
        with libarchive.file_reader(str(path)) as archive:
            for entry in archive:
                if entry.isfile and not is_ignored(entry.pathname):
                    yield entry.pathname, b"".join(entry.get_blocks())
    except libarchive.ArchiveError as exc:
        raise ImportFailed(f"arhiva je oštećena ili nepodržana ({exc})") from exc


def _scan_image(page: pdfium.PdfPage) -> tuple[str, bytes] | None:
    """Skenirana stranica (jedna slika preko cele strane): ugrađena slika bez ponovne kompresije.

    JPEG se uzima bajt po bajt; ostale slike (Flate i sl.) u svojoj rezoluciji, kao PNG.
    """
    images = list(page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,), max_depth=1))
    if len(images) != 1:
        return None
    image = images[0]
    left, bottom, right, top = image.get_bounds()
    width, height = page.get_size()
    if (right - left) * (top - bottom) < 0.9 * width * height:
        return None
    if image.get_filters() == ["DCTDecode"]:
        return "jpeg", bytes(image.get_data(decode_simple=False))
    buffer = io.BytesIO()
    image.get_bitmap(render=False).to_pil().save(buffer, "PNG")
    return "png", buffer.getvalue()


def _iter_pdf(path: Path) -> Iterator[tuple[str, bytes]]:
    try:
        document = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        raise ImportFailed(f"PDF je oštećen ({exc})") from exc
    try:
        for number in range(len(document)):
            page = document[number]
            name = f"strana-{number + 1:04d}"
            scan = _scan_image(page)
            if scan:
                yield f"{name}.{scan[0]}", scan[1]
                continue
            buffer = io.BytesIO()
            page.render(scale=PDF_DPI / 72).to_pil().save(buffer, "PNG")
            yield f"{name}.png", buffer.getvalue()
    finally:
        document.close()


def collect_sources(files: Iterable[tuple[Path, str]]) -> list[tuple[str, bytes]]:
    """Skupi kandidate za stranice iz uploadovanih fajlova, prirodno sortirane.

    `files` su parovi (putanja na disku, originalno ime). Imena iz fajlova i arhiva služe samo
    za sortiranje i prikaz, nikad kao putanje na disku.
    """
    budget = _Budget()
    collected = []
    for path, original_name in files:
        try:
            kind = detect_format(path)
            if kind == "image":
                entries: Iterable[tuple[str, bytes]] = [("", path.read_bytes())]
            elif kind == "pdf":
                entries = _iter_pdf(path)
            else:
                entries = _iter_archive(path)
            for name, data in entries:
                budget.take(len(data))
                display = f"{original_name}/{name}" if name else original_name
                key = (natural_key(original_name), natural_key(name))
                collected.append((key, display, data))
        except ImportFailed as exc:
            raise ImportFailed(f"{original_name}: {exc}") from exc
    collected.sort(key=lambda item: item[0])
    return [(display, data) for _, display, data in collected]


def _encode(image: Image.Image, format_: str, **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format_, **options)
    return buffer.getvalue()


def _thumbnail(image: Image.Image) -> bytes:
    thumbnail = image.convert("RGB")
    thumbnail.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 10))
    return _encode(thumbnail, "WEBP", quality=80)


def prepare_page(name: str, data: bytes) -> PreparedPage | None:
    """Pripremi stranicu iz bajtova slike. Vraća None ako podatak nije slika."""
    try:
        image = Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        return None
    except Image.DecompressionBombError as exc:
        raise ImportFailed(f"{name}: slika je prevelika") from exc
    with image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ImportFailed(f"{name}: slika je prevelika ({image.width}×{image.height})")
        try:
            image.load()
        except OSError as exc:
            raise ImportFailed(f"{name}: slika je oštećena ({exc})") from exc
        format_ = image.format
        rotated = image.getexif().get(0x0112, 1) != 1
        page_image = ImageOps.exif_transpose(image) if rotated else image
        if format_ in BROWSER_FORMATS and not rotated:
            extension, output = BROWSER_FORMATS[format_], data
        else:
            if page_image.mode not in PNG_MODES:
                page_image = page_image.convert("RGB")
            extension, output = ".png", _encode(page_image, "PNG")
        return PreparedPage(
            source_name=name,
            data=output,
            extension=extension,
            width=page_image.width,
            height=page_image.height,
            thumbnail=_thumbnail(page_image),
        )
