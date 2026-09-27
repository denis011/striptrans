import io
import zipfile

import img2pdf
import libarchive
import pytest
from PIL import Image

from app.services import importer
from app.services.importer import ImportFailed, collect_sources, natural_key, prepare_page


def image_bytes(format_="JPEG", size=(60, 90), noise=False, **options) -> bytes:
    image = Image.effect_noise(size, 60) if noise else Image.new("L", size, 128)
    buffer = io.BytesIO()
    image.save(buffer, format_, **options)
    return buffer.getvalue()


def names(sources) -> list[str]:
    return [name for name, _ in sources]


def write_zip(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return path


def write_libarchive(path, format_name, entries):
    with libarchive.file_writer(str(path), format_name) as archive:
        for name, data in entries:
            archive.add_file_from_memory(name, len(data), data)
    return path


def test_natural_key_orders_numbers_like_humans():
    files = ["100.jpg", "002.jpg", "10.jpg", "9.jpg", "001.jpg"]
    assert sorted(files, key=natural_key) == ["001.jpg", "002.jpg", "9.jpg", "10.jpg", "100.jpg"]


def test_zip_with_cbr_extension_is_read_by_content(tmp_path):
    jpg = image_bytes()
    entries = [("100.jpg", jpg), ("001.jpg", jpg), ("099.jpg", jpg)]
    path = write_zip(tmp_path / "strip.cbr", entries)

    assert names(collect_sources([(path, "strip.cbr")])) == [
        "strip.cbr/001.jpg",
        "strip.cbr/099.jpg",
        "strip.cbr/100.jpg",
    ]


def test_system_files_are_skipped(tmp_path):
    jpg = image_bytes()
    entries = [
        ("001.jpg", jpg),
        ("__MACOSX/._001.jpg", b"junk"),
        ("Thumbs.db", b"junk"),
        ("001.jpg:Zone.Identifier", b"[ZoneTransfer]"),
        (".hidden.jpg", jpg),
    ]
    path = write_zip(tmp_path / "a.cbz", entries)

    assert names(collect_sources([(path, "a.cbz")])) == ["a.cbz/001.jpg"]


@pytest.mark.parametrize("format_name", ["7zip", "ustar"])
def test_7z_and_tar_archives(tmp_path, format_name):
    jpg = image_bytes()
    path = write_libarchive(tmp_path / "arhiva", format_name, [("2.jpg", jpg), ("1.jpg", jpg)])

    assert names(collect_sources([(path, "x")])) == ["x/1.jpg", "x/2.jpg"]


def test_multiple_uploaded_images_are_sorted_naturally(tmp_path):
    (tmp_path / "u1").write_bytes(image_bytes("PNG"))
    (tmp_path / "u2").write_bytes(image_bytes())

    sources = collect_sources([(tmp_path / "u1", "strana10.png"), (tmp_path / "u2", "strana2.jpg")])

    assert names(sources) == ["strana2.jpg", "strana10.png"]


def test_pdf_scan_is_extracted_without_recompression(tmp_path):
    jpg = image_bytes(size=(600, 850), noise=True)
    (tmp_path / "s.pdf").write_bytes(img2pdf.convert(jpg))

    [(name, data)] = collect_sources([(tmp_path / "s.pdf", "s.pdf")])

    assert name == "s.pdf/strana-0001.jpeg"
    assert data == jpg


def test_pdf_png_scan_keeps_its_pixels(tmp_path):
    image = Image.effect_noise((300, 420), 60).convert("L")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    (tmp_path / "p.pdf").write_bytes(img2pdf.convert(buffer.getvalue()))

    [(name, data)] = collect_sources([(tmp_path / "p.pdf", "p.pdf")])

    assert name == "p.pdf/strana-0001.png"
    assert Image.open(io.BytesIO(data)).tobytes() == image.tobytes()


def vector_pdf() -> bytes:
    """Strana 72×144 pt sa jednom linijom, bez slika (kao PDF iz programa za prelom)."""
    stream = b"0 0 m 72 144 l S"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 144] /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return out


def test_pdf_vector_page_is_rendered_at_300_dpi(tmp_path):
    (tmp_path / "v.pdf").write_bytes(vector_pdf())

    [(_, data)] = collect_sources([(tmp_path / "v.pdf", "v.pdf")])

    assert Image.open(io.BytesIO(data)).size == (300, 600)


def test_unsupported_file_is_rejected(tmp_path):
    (tmp_path / "t").write_text("ovo nije strip")

    with pytest.raises(ImportFailed, match="beleske.txt: nepodržan format"):
        collect_sources([(tmp_path / "t", "beleske.txt")])


def test_truncated_archive_is_rejected(tmp_path):
    good = write_zip(tmp_path / "g.zip", [("001.jpg", image_bytes(size=(400, 400), noise=True))])
    data = good.read_bytes()
    (tmp_path / "bad").write_bytes(data[: len(data) // 2])

    with pytest.raises(ImportFailed, match="bad.cbz"):
        collect_sources([(tmp_path / "bad", "bad.cbz")])


def test_file_count_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MAX_FILES", 2)
    jpg = image_bytes()
    path = write_zip(tmp_path / "a.zip", [(f"{i}.jpg", jpg) for i in range(3)])

    with pytest.raises(ImportFailed, match="previše fajlova"):
        collect_sources([(path, "a.zip")])


def test_prepare_page_keeps_original_jpeg_bytes_and_makes_thumbnail():
    jpg = image_bytes(size=(1801, 2457))

    page = prepare_page("001.jpg", jpg)

    assert (page.data, page.extension, page.width, page.height) == (jpg, ".jpg", 1801, 2457)
    thumbnail = Image.open(io.BytesIO(page.thumbnail))
    assert (thumbnail.format, thumbnail.width) == ("WEBP", 240)


def test_prepare_page_converts_tiff_to_png():
    page = prepare_page("s.tif", image_bytes("TIFF"))

    assert page.extension == ".png"
    assert Image.open(io.BytesIO(page.data)).format == "PNG"


def test_prepare_page_applies_exif_orientation():
    exif = Image.Exif()
    exif[0x0112] = 6

    page = prepare_page("r.jpg", image_bytes(size=(100, 50), exif=exif.tobytes()))

    assert (page.width, page.height, page.extension) == (50, 100, ".png")


def test_prepare_page_skips_non_images():
    assert prepare_page("ComicInfo.xml", b"<ComicInfo/>") is None


def test_prepare_page_rejects_corrupted_image():
    data = image_bytes(size=(400, 400), noise=True)

    with pytest.raises(ImportFailed, match="oštećena"):
        prepare_page("x.jpg", data[: len(data) // 2])


def test_prepare_page_rejects_huge_image(monkeypatch):
    monkeypatch.setattr(importer, "MAX_IMAGE_PIXELS", 100)

    with pytest.raises(ImportFailed, match="prevelika"):
        prepare_page("x.png", image_bytes("PNG", size=(20, 20)))
