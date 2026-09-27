"""Izvoz scenarija za lektora (Faza 8a): tabela oblačić po oblačić, van aplikacije.

Lektor čita i ispravlja prevod bez editora: HTML se otvara u browseru i štampa, a CSV se otvara
u tabeli (Excel, LibreOffice). Redosled je isti kao u editoru — po stranicama i redosledu čitanja.
"""

import collections
import csv
import html
import io
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Page, Project, TextBlock

KINDS = {
    "speech": "govor",
    "thought": "misao",
    "caption": "naracija",
    "sfx": "onomatopeja",
    "other": "natpis",
    "title": "naslov",
}
STATUSES = {"none": "bez prevoda", "draft": "nacrt", "edited": "izmenjeno", "approved": "odobreno"}
COLUMNS = ("strana", "blok", "vrsta", "original", "prevod", "status", "napomena")


def title(project: Project) -> str:
    parts = [project.series.name]
    if project.issue_number:
        parts.append(project.issue_number)
    if project.translated_title or project.original_title:
        parts.append(project.translated_title or project.original_title or "")
    return " — ".join(part for part in parts if part)


def _note(block: TextBlock) -> str:
    notes = []
    if block.translation_too_long:
        notes.append("prevod duži od originala")
    if block.needs_review:
        notes.append("OCR za proveru")
    return ", ".join(notes)


def rows(session: Session, project: Project, skipped: bool = False) -> list[dict]:
    """Redovi scenarija: po stranici, u redosledu čitanja; preskočene stranice se izostavljaju."""
    pages = session.scalars(
        select(Page)
        .where(Page.project_id == project.id, Page.kind == "original")
        .order_by(Page.position)
    )
    result = []
    for page in pages:
        if page.skip and not skipped:
            continue
        blocks = session.scalars(
            select(TextBlock)
            .where(TextBlock.page_id == page.id)
            .order_by(TextBlock.position, TextBlock.id)
        )
        for block in blocks:
            if not (block.text.strip() or block.translation.strip()):
                continue
            result.append(
                {
                    "strana": page.position,
                    "blok": block.position,
                    "vrsta": KINDS.get(block.kind, block.kind),
                    "original": block.text.strip(),
                    "prevod": block.translation.strip(),
                    "status": STATUSES.get(block.translation_status, block.translation_status),
                    "napomena": _note(block),
                }
            )
    return result


def to_csv(session: Session, project: Project, skipped: bool = False) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows(session, project, skipped))
    return buffer.getvalue().encode("utf-8-sig")  # BOM: Excel prepoznaje naša slova


STYLE = """
  body { font: 15px/1.5 system-ui, sans-serif; margin: 24px auto; max-width: 1000px;
         color: #1c1917; }
  h1 { font-size: 1.4rem; margin-bottom: 0.2em; }
  p.meta { color: #57534e; margin-top: 0; }
  h2 { font-size: 1.05rem; margin: 1.6em 0 0.4em; border-bottom: 1px solid #d6d3d1; }
  h2 a { color: inherit; text-decoration: none; }
  h2 a:hover { text-decoration: underline; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #d6d3d1; padding: 6px 8px; vertical-align: top; text-align: left; }
  th { background: #f5f5f4; font-weight: 600; }
  td.original { color: #57534e; width: 38%; }
  td.prevod { width: 38%; }
  td.blok, td.vrsta { white-space: nowrap; width: 1%; }
  td.napomena { color: #b45309; }
  tr.nacrt td.prevod { background: #fffbeb; }
  tr.bez-prevoda td.prevod { background: #fef2f2; }
  @media print { body { margin: 0; max-width: none; }
    h2 { page-break-after: avoid; } tr { page-break-inside: avoid; } }
"""


def _summary(entries: list[dict]) -> str:
    """Koliko je blokova, koliko ih čeka prevod i koliko je odobreno."""
    counts = collections.Counter(entry["status"] for entry in entries)
    parts = [f"{len(entries)} blokova"]
    for status in ("bez prevoda", "nacrt", "izmenjeno", "odobreno"):
        if counts[status]:
            parts.append(f"{counts[status]} {status}")
    return " · ".join(parts)


def to_html(session: Session, project: Project, skipped: bool = False, app_url: str = "") -> bytes:
    """Scenario kao jedna HTML strana: po stranici tabela original / prevod."""
    entries = rows(session, project, skipped)
    parts = [
        "<!doctype html><html lang='sr'><head><meta charset='utf-8'>",
        f"<title>Scenario — {html.escape(title(project))}</title>",
        f"<style>{STYLE}</style></head><body>",
        f"<h1>{html.escape(title(project))}</h1>",
        f"<p class='meta'>Scenario za lekturu · {_summary(entries)} · "
        f"{datetime.now():%d.%m.%Y.}</p>",
    ]
    page = None
    for entry in entries:
        if entry["strana"] != page:
            if page is not None:
                parts.append("</tbody></table>")
            page = entry["strana"]
            link = f"{app_url.rstrip('/')}/projects/{project.id}/pages/{page}" if app_url else ""
            label = f"Strana {page}"
            heading = f"<a href='{html.escape(link)}'>{label}</a>" if link else label
            parts.append(f"<h2>{heading}</h2>")
            parts.append(
                "<table><thead><tr><th>Blok</th><th>Vrsta</th><th>Original</th>"
                "<th>Prevod</th><th>Napomena</th></tr></thead><tbody>"
            )
        draft = "nacrt" if entry["status"] == "nacrt" else ""
        css = "bez-prevoda" if not entry["prevod"] else draft
        cells = "".join(
            f"<td class='{name}'>{html.escape(str(entry[name])).replace(chr(10), '<br>')}</td>"
            for name in ("blok", "vrsta", "original", "prevod", "napomena")
        )
        parts.append(f"<tr class='{css}'>{cells}</tr>")
    parts.append("</tbody></table>" if page is not None else "<p>Nema blokova sa tekstom.</p>")
    parts.append("</body></html>")
    return "\n".join(parts).encode("utf-8")


def filename(project: Project, extension: str) -> str:
    parts = [project.series.name, project.issue_number or "", "scenario"]
    slug = "-".join(part for part in parts if part).lower()
    table = str.maketrans("čćžšđ ", "cczsd-")
    keep = "abcdefghijklmnopqrstuvwxyz0123456789-"
    cleaned = "".join(ch for ch in slug.translate(table) if ch in keep)
    return f"{cleaned.strip('-') or 'scenario'}.{extension}"
