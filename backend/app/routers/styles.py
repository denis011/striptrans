"""Stilovi prevoda (strana Podešavanja): više sačuvanih, jedan aktivan."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import SessionDep
from app.models import TranslationStyle
from app.schemas import StyleIn, StyleOut, StylePatch
from app.services import styles

router = APIRouter(prefix="/api/translation-styles", tags=["styles"])


def _out(style: TranslationStyle) -> StyleOut:
    return StyleOut(
        id=style.id,
        name=style.name,
        text=styles.style_text(style),
        builtin=style.builtin,
        active=style.active,
        changed=style.builtin and style.text is not None,
    )


def _style(session: Session, style_id: int) -> TranslationStyle:
    style = session.get(TranslationStyle, style_id)
    if style is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stil ne postoji")
    return style


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "stil sa tim imenom već postoji") from None


@router.get("")
def list_styles(session: SessionDep) -> list[StyleOut]:
    query = select(TranslationStyle).order_by(
        TranslationStyle.builtin.desc(), TranslationStyle.name
    )
    return [_out(style) for style in session.scalars(query)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_style(data: StyleIn, session: SessionDep) -> StyleOut:
    style = TranslationStyle(name=data.name.strip(), text=data.text)
    session.add(style)
    _commit(session)
    return _out(style)


@router.patch("/{style_id}")
def update_style(style_id: int, data: StylePatch, session: SessionDep) -> StyleOut:
    style = _style(session, style_id)
    if data.name is not None:
        style.name = data.name.strip()
    if data.text is not None:
        style.text = data.text
    _commit(session)
    return _out(style)


@router.post("/{style_id}/activate")
def activate_style(style_id: int, session: SessionDep) -> StyleOut:
    """Aktivni stil koristi svaki sledeći prevod (stranica, projekat, blok)."""
    style = _style(session, style_id)
    styles.activate(session, style)
    session.commit()
    return _out(style)


@router.post("/{style_id}/reset")
def reset_style(style_id: int, session: SessionDep) -> StyleOut:
    """Ugrađeni stil se vraća na podrazumevani tekst iz aplikacije."""
    style = _style(session, style_id)
    if not style.builtin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "samo ugrađeni stil ima podrazumevani tekst"
        )
    style.text = None
    session.commit()
    return _out(style)


@router.delete("/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_style(style_id: int, session: SessionDep) -> Response:
    style = _style(session, style_id)
    if style.builtin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ugrađeni stil se ne briše")
    if style.active:  # bez aktivnog stila prevod koristi ugrađeni
        builtin = session.scalar(select(TranslationStyle).where(TranslationStyle.builtin))
        if builtin is not None:
            styles.activate(session, builtin)
    session.delete(style)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
