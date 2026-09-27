"""Fontovi: spisak (ugrađeni i korisnički), fajl fonta, dodavanje i brisanje korisničkih."""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, update

from app.deps import SessionDep, SettingsDep
from app.models import Font, Series
from app.schemas import FontOut
from app.services.fonts import (
    BUILTIN,
    BUILTIN_DIR,
    USER_PREFIX,
    FontRejected,
    builtin,
    inspect_font,
    user_font,
)

router = APIRouter(prefix="/api/fonts", tags=["fonts"])

MAX_FONT_BYTES = 20 * 1024 * 1024
FONT_TYPES = {b"\x00\x01\x00\x00": ".ttf", b"true": ".ttf", b"OTTO": ".otf"}
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def _user_out(font: Font) -> FontOut:
    key = f"{USER_PREFIX}{font.id}"
    # ključ se posle brisanja može ponoviti, a fajl se kešira: jedinstveno ime fajla ide u adresu
    version = Path(font.path).stem[:12]
    url = f"/api/fonts/{key}/file?v={version}"
    return FontOut(key=key, name=font.name, kind=font.kind, builtin=False, url=url)


@router.get("")
def list_fonts(session: SessionDep) -> list[FontOut]:
    fonts = [
        FontOut(key=f.key, name=f.name, kind=f.kind, builtin=True, url=f"/api/fonts/{f.key}/file")
        for f in BUILTIN
    ]
    return fonts + [_user_out(font) for font in session.scalars(select(Font).order_by(Font.name))]


@router.get("/{key}/file")
def font_file(key: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    if found := builtin(key):
        return FileResponse(BUILTIN_DIR / found.filename, media_type="font/ttf", headers=IMMUTABLE)
    if font := user_font(session, key):
        path = Path(settings.data_dir, font.path)
        media = "font/otf" if path.suffix == ".otf" else "font/ttf"
        return FileResponse(path, media_type=media, headers=IMMUTABLE)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "font ne postoji")


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_font(
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "dialogue",
) -> FontOut:
    """Dodaj TTF/OTF; odbija se font kome fale srpska slova ili su mu glifovi prazni."""
    if kind not in ("dialogue", "sfx", "title"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "vrsta mora biti dialogue ili sfx")
    data = await file.read(MAX_FONT_BYTES + 1)
    if len(data) > MAX_FONT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "font je prevelik")
    extension = FONT_TYPES.get(data[:4])
    if extension is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "fajl nije TTF ili OTF font")
    try:
        name, missing = inspect_font(data)
    except FontRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'fontu „{name}" fale slova ili su prazna: {" ".join(missing)}',
        )
    relative = Path("fonts", uuid.uuid4().hex + extension)
    target = Path(settings.data_dir, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    font = Font(name=name[:200], path=str(relative), kind=kind)
    session.add(font)
    session.commit()
    return _user_out(font)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_font(key: str, session: SessionDep, settings: SettingsDep) -> Response:
    font = user_font(session, key)
    if font is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "korisnički font ne postoji")
    Path(settings.data_dir, font.path).unlink(missing_ok=True)
    # serijali koji su ga koristili vraćaju se na podrazumevani font
    for column in (Series.dialogue_font, Series.sfx_font):
        session.execute(update(Series).where(column == key).values({column: None}))
    session.delete(font)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
