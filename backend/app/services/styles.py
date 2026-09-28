"""Stilovi prevoda (strana Podešavanja) i uputstvo serijala, dodaju se na tehnički deo prompta."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Series, TranslationStyle
from app.services.translation import DEFAULT_STYLE, Style


def style_text(style: TranslationStyle) -> str:
    return DEFAULT_STYLE if style.text is None else style.text


def active(session: Session) -> TranslationStyle | None:
    return session.scalar(select(TranslationStyle).where(TranslationStyle.active))


def for_series(session: Session, series: Series, style_id: int | None = None) -> Style:
    """Stil za prevod: izabran (za probni prevod) ili aktivan, plus uputstvo serijala."""
    chosen = session.get(TranslationStyle, style_id) if style_id else active(session)
    text = style_text(chosen) if chosen else DEFAULT_STYLE
    return Style(text=text, series_notes=series.translation_notes or "")


def activate(session: Session, style: TranslationStyle) -> None:
    for other in session.scalars(select(TranslationStyle).where(TranslationStyle.active)):
        other.active = False
    style.active = True
