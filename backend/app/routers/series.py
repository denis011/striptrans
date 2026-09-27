from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import SessionDep
from app.models import Series
from app.schemas import SeriesIn, SeriesOut, SeriesPatch
from app.services.fonts import font_exists

router = APIRouter(prefix="/api/series", tags=["series"])


@router.get("")
def list_series(session: SessionDep) -> list[SeriesOut]:
    return session.scalars(select(Series).order_by(Series.name)).all()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_series(data: SeriesIn, session: SessionDep) -> SeriesOut:
    series = Series(**data.model_dump())
    session.add(series)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "serijal sa tim imenom već postoji") from None
    return series


@router.patch("/{series_id}")
def update_series(series_id: int, data: SeriesPatch, session: SessionDep) -> SeriesOut:
    """Podrazumevani fontovi serijala (za govor i za onomatopeje) i ukošena naracija."""
    series = session.get(Series, series_id)
    if series is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serijal ne postoji")
    changes = data.model_dump(exclude_unset=True)
    if changes.pop("caption_italic", None) is not None:
        series.caption_italic = bool(data.caption_italic)
    for field, key in changes.items():
        if key is not None and not font_exists(session, key):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f'font „{key}" ne postoji')
        setattr(series, field, key)
    session.commit()
    return series
