"""Zlatni set za benchmark Faze 2 (tekst, tip i redosled blokova na izabranim stranicama).

  prepare --project P --pages 5,6 --out DIR   detekcija bez OCR-a + slike za ručni prepis
  apply   --project P --file prepis.json      upis prepisa u blokove projekta
  export  --project P --pages 5,6             JSON zlatnog seta na standardni izlaz
  pairs   --project P --reference-project R --pages 5,6
  restore --project P --file zlatni.json      vrati blokove iz izvezenog zlatnog seta
  restore-pairs --project R --source-project P --file parovi.json
                                              vrati tekst referentnog izdanja na okvire originala
                                              upareni blokovi originala i referentnog izdanja (JSON)

Format za apply: {"pages": [{"position": 5, "delete": [id, ...], "blocks": [
    {"id": 12, "kind": "speech", "text": "..."},                       # postojeći blok
    {"id": null, "kind": "sfx", "text": "SWACK", "box": [x, y, w, h]}  # nov blok, okvir približan
]}]} — redosled u listi je redosled čitanja; svaki blok stranice mora biti naveden ili obrisan.
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import make_engine
from app.models import Page, TextBlock
from app.routers.blocks import page_blocks
from app.services.alignment import align_boxes
from app.services.page_processing import detect_blocks

GRID = 200  # korak koordinatne mreže u pikselima stranice
OVERVIEW_HEIGHT = 1100
SHEET_WIDTH = 1400
SHEET_SCALE = 0.8


def get_page(session: Session, project: int, position: int) -> Page:
    page = session.scalar(
        select(Page).where(
            Page.project_id == project, Page.kind == "original", Page.position == position
        )
    )
    if page is None:
        raise SystemExit(f"projekat {project} nema stranicu {position}")
    return page


def render_overview(image: Image.Image, blocks: list[TextBlock], path: Path) -> None:
    canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    small = ImageFont.load_default(size=28)
    for x in range(0, canvas.width, GRID):
        draw.line([(x, 0), (x, canvas.height)], fill=(170, 170, 255), width=2)
        draw.text((x + 4, 4), str(x), fill=(60, 60, 255), font=small)
    for y in range(0, canvas.height, GRID):
        draw.line([(0, y), (canvas.width, y)], fill=(170, 170, 255), width=2)
        draw.text((4, y + 4), str(y), fill=(60, 60, 255), font=small)
    big = ImageFont.load_default(size=60)
    for block in blocks:
        box = [block.x, block.y, block.x + block.width, block.y + block.height]
        draw.rectangle(box, outline=(230, 0, 0), width=7)
        draw.text((block.x - 50, block.y - 30), str(block.position), fill=(230, 0, 0), font=big)
    scale = OVERVIEW_HEIGHT / canvas.height
    canvas.resize((round(canvas.width * scale), OVERVIEW_HEIGHT)).save(path)


def render_sheet(image: Image.Image, blocks: list[TextBlock], path: Path) -> None:
    """Isečci blokova u redovima, sa rednim brojem iznad svakog."""
    font = ImageFont.load_default(size=34)
    pieces = []
    for block in blocks:
        margin = 12
        crop = image.crop(
            (
                max(0, round(block.x - margin)),
                max(0, round(block.y - margin)),
                min(image.width, round(block.x + block.width + margin)),
                min(image.height, round(block.y + block.height + margin)),
            )
        ).convert("L")
        size = (max(1, round(crop.width * SHEET_SCALE)), max(1, round(crop.height * SHEET_SCALE)))
        pieces.append((block.position, crop.resize(size, Image.Resampling.LANCZOS)))
    rows, row, row_width = [], [], 0
    for piece in pieces:
        width = min(piece[1].width, SHEET_WIDTH)
        if row and row_width + width + 20 > SHEET_WIDTH:
            rows.append(row)
            row, row_width = [], 0
        row.append(piece)
        row_width += width + 20
    if row:
        rows.append(row)
    label = 44
    height = sum(label + max(p[1].height for p in r) + 20 for r in rows) or 1
    sheet = Image.new("L", (SHEET_WIDTH, height), 255)
    draw = ImageDraw.Draw(sheet)
    y = 0
    for r in rows:
        x = 0
        for position, piece in r:
            draw.text((x, y), f"#{position}", fill=0, font=font)
            sheet.paste(piece, (x, y + label))
            draw.rectangle([x, y + label, x + piece.width, y + label + piece.height], outline=128)
            x += piece.width + 20
        y += label + max(p[1].height for p in r) + 20
    sheet.save(path)


def prepare(session: Session, settings, args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for position in args.pages:
        page = get_page(session, args.project, position)
        blocks = detect_blocks(session, settings, page)
        session.commit()
        with Image.open(Path(settings.data_dir, page.image_path)) as image:
            render_overview(image, blocks, out / f"p{position:03d}-overview.png")
            render_sheet(image, blocks, out / f"p{position:03d}-crops.png")
        ids = " ".join(f"#{b.position}={b.id}" for b in blocks)
        print(f"str. {position} (page id {page.id}, {page.width}×{page.height}): {ids}")


def apply(session: Session, args) -> None:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    for entry in data["pages"]:
        page = get_page(session, args.project, entry["position"])
        existing = {block.id: block for block in page_blocks(session, page.id)}
        listed = {item["id"] for item in entry["blocks"] if item.get("id")}
        deleted = set(entry.get("delete", []))
        if missing := set(existing) - listed - deleted:
            raise SystemExit(
                f"str. {entry['position']}: blokovi nisu navedeni ni obrisani: {missing}"
            )
        for block_id in deleted:
            session.delete(existing[block_id])
        for position, item in enumerate(entry["blocks"], start=1):
            if item.get("id"):
                block = existing[item["id"]]
                block.needs_review = False
            else:
                x, y, width, height = item["box"]
                block = TextBlock(page_id=page.id, x=x, y=y, width=width, height=height)
                block.source = "manual"
                block.needs_review = True  # približan okvir, proveriti u editoru
                session.add(block)
            block.position = position
            block.kind = item["kind"]
            block.text = item["text"]
            block.ocr_text = None
            block.ocr_model = None
        session.commit()
        print(f"str. {entry['position']}: {len(entry['blocks'])} blokova, obrisano {len(deleted)}")


def export(session: Session, args) -> None:
    pages = []
    for position in args.pages:
        page = get_page(session, args.project, position)
        blocks = page_blocks(session, page.id)
        pages.append(
            {
                "position": position,
                "entry": page.source_name.rsplit("/", 1)[-1],
                "width": page.width,
                "height": page.height,
                "reviewed": page.ocr_reviewed,
                "blocks": [
                    {
                        "position": b.position,
                        "kind": b.kind,
                        "box": [
                            round(b.x, 1),
                            round(b.y, 1),
                            round(b.width, 1),
                            round(b.height, 1),
                        ],
                        "text": b.text,
                    }
                    for b in blocks
                ],
            }
        )
    archive = pages and session.get(Page, get_page(session, args.project, args.pages[0]).id)
    source = archive.source_name.rsplit("/", 1)[0] if archive else ""
    json.dump({"archive": source, "pages": pages}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def export_pairs(session: Session, args) -> None:
    """Blokovi originala upareni sa blokovima referentnog izdanja iste stranice, po položaju."""
    pages = []
    for position in args.pages:
        original = get_page(session, args.project, position)
        reference = get_page(session, args.reference_project, position)
        source = [b for b in page_blocks(session, original.id) if b.text.strip()]
        target = [b for b in page_blocks(session, reference.id) if b.text.strip()]
        matches = align_boxes(
            [(b.x, b.y, b.width, b.height) for b in source],
            (original.width, original.height),
            [(b.x, b.y, b.width, b.height) for b in target],
            (reference.width, reference.height),
            [b.kind for b in source],
            [b.kind for b in target],
        )
        pages.append(
            {
                "position": position,
                "reviewed": reference.ocr_reviewed,
                "pairs": [
                    {
                        "position": source[i].position,
                        "kind": source[i].kind,
                        "source": source[i].text,
                        "target": target[j].text,
                    }
                    for i, j in sorted(matches.items())
                ],
                "unmatched_source": [
                    {"position": b.position, "kind": b.kind, "text": b.text}
                    for i, b in enumerate(source)
                    if i not in matches
                ],
                "unmatched_target": [
                    {"position": b.position, "kind": b.kind, "text": b.text}
                    for j, b in enumerate(target)
                    if j not in set(matches.values())
                ],
            }
        )
    json.dump({"pages": pages}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def restore(session: Session, args) -> None:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    for entry in data["pages"]:
        page = get_page(session, args.project, entry["position"])
        session.execute(delete(TextBlock).where(TextBlock.page_id == page.id))
        for item in entry["blocks"]:
            x, y, width, height = item["box"]
            session.add(
                TextBlock(
                    page_id=page.id,
                    position=item["position"],
                    kind=item["kind"],
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    text=item["text"],
                    source="manual",
                    needs_review=False,
                )
            )
        page.ocr_reviewed = entry["reviewed"]
        print(f"str. {entry['position']}: {len(entry['blocks'])} blokova")
    session.commit()


def restore_pairs(session: Session, args) -> None:
    """Tekst referentnog izdanja iz parova, na okvirima originala preračunatim na referentnu stranicu."""  # noqa: E501
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    for entry in data["pages"]:
        source_page = get_page(session, args.source_project, entry["position"])
        target_page = get_page(session, args.project, entry["position"])
        source = {block.position: block for block in page_blocks(session, source_page.id)}
        scale_x = target_page.width / source_page.width
        scale_y = target_page.height / source_page.height
        session.execute(delete(TextBlock).where(TextBlock.page_id == target_page.id))
        for position, pair in enumerate(entry["pairs"], start=1):
            block = source[pair["position"]]
            session.add(
                TextBlock(
                    page_id=target_page.id,
                    position=position,
                    kind=block.kind,
                    x=block.x * scale_x,
                    y=block.y * scale_y,
                    width=block.width * scale_x,
                    height=block.height * scale_y,
                    text=pair["target"],
                    source="manual",
                    needs_review=False,
                )
            )
        target_page.ocr_reviewed = entry["reviewed"]
        lost = entry.get("unmatched_target", [])
        print(
            f"str. {entry['position']}: {len(entry['pairs'])} blokova"
            + (f", bez okvira: {lost}" if lost else "")
        )
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "command", choices=["prepare", "apply", "export", "pairs", "restore", "restore-pairs"]
    )
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--pages", type=lambda v: [int(p) for p in v.split(",")], default=[])
    parser.add_argument("--out", default="/tmp/gold")
    parser.add_argument("--file")
    parser.add_argument("--reference-project", type=int)
    parser.add_argument("--source-project", type=int)
    args = parser.parse_args()
    settings = get_settings()
    with sessionmaker(make_engine(settings.database_url))() as session:
        if args.command == "prepare":
            prepare(session, settings, args)
        elif args.command == "apply":
            apply(session, args)
        elif args.command == "restore":
            restore(session, args)
        elif args.command == "restore-pairs":
            restore_pairs(session, args)
        elif args.command == "pairs":
            export_pairs(session, args)
        else:
            export(session, args)


if __name__ == "__main__":
    main()
