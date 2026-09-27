from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import SessionDep, SettingsDep
from app.models import GlossaryEntry, Job, Project, Series
from app.schemas import (
    GlossaryIn,
    GlossaryOut,
    GlossaryPatch,
    GlossaryStatus,
    GlossarySuggestRequest,
    JobOut,
)
from app.services.glossary_suggest import clean_term

router = APIRouter(prefix="/api", tags=["glossary"])


def _entry(session: Session, entry_id: int) -> GlossaryEntry:
    entry = session.get(GlossaryEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stavka glosara ne postoji")
    return entry


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "ista stavka već postoji u glosaru") from None


@router.get("/series/{series_id}/glossary")
def list_glossary(
    series_id: int,
    session: SessionDep,
    status_filter: Annotated[GlossaryStatus | None, Query(alias="status")] = None,
) -> list[GlossaryOut]:
    if session.get(Series, series_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serijal ne postoji")
    query = select(GlossaryEntry).where(GlossaryEntry.series_id == series_id)
    if status_filter:
        query = query.where(GlossaryEntry.status == status_filter)
    return session.scalars(query.order_by(GlossaryEntry.source, GlossaryEntry.target)).all()


@router.post("/series/{series_id}/glossary", status_code=status.HTTP_201_CREATED)
def create_glossary_entry(series_id: int, data: GlossaryIn, session: SessionDep) -> GlossaryOut:
    if session.get(Series, series_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serijal ne postoji")
    entry = GlossaryEntry(
        series_id=series_id,
        source=clean_term(data.source),
        target=clean_term(data.target),
        kind=data.kind,
        note=data.note,
        status="approved",
        origin="manual",
    )
    session.add(entry)
    _commit(session)
    return entry


@router.patch("/glossary/{entry_id}")
def update_glossary_entry(entry_id: int, data: GlossaryPatch, session: SessionDep) -> GlossaryOut:
    entry = _entry(session, entry_id)
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(entry, field, clean_term(value) if field in ("source", "target") else value)
    _commit(session)
    return entry


@router.delete("/glossary/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_glossary_entry(entry_id: int, session: SessionDep) -> Response:
    session.delete(_entry(session, entry_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/series/{series_id}/glossary/suggest", status_code=status.HTTP_202_ACCEPTED)
def suggest_glossary(
    series_id: int, data: GlossarySuggestRequest, session: SessionDep, settings: SettingsDep
) -> JobOut:
    """Posao koji iz uparenih blokova originala i referentnog izdanja predlaže stavke glosara."""
    if session.get(Series, series_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serijal ne postoji")
    for project_id in (data.project_id, data.reference_project_id):
        if session.get(Project, project_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"projekat {project_id} ne postoji")
    job = Job(
        type="glossary_suggest",
        project_id=data.project_id,
        payload={
            "series_id": series_id,
            "project_id": data.project_id,
            "reference_project_id": data.reference_project_id,
            "model": data.model or settings.glossary_model,
        },
    )
    session.add(job)
    session.commit()
    return job
