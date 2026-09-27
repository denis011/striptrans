"""Glosar onomatopeja (zajednički za sve serijale) i primena na projekat."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import SessionDep
from app.models import Project, SfxEntry
from app.schemas import SfxApplied, SfxIn, SfxMissing, SfxOut, SfxPatch
from app.services import sfx_glossary
from app.services.glossary_suggest import clean_term

router = APIRouter(prefix="/api", tags=["sfx"])


def _entry(session: Session, entry_id: int) -> SfxEntry:
    entry = session.get(SfxEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "onomatopeja ne postoji u glosaru")
    return entry


def _source(value: str) -> str:
    source = sfx_glossary.key(value)
    if not source:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "onomatopeja nema slova")
    return source


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "onomatopeja već postoji u glosaru") from None


@router.get("/sfx-glossary")
def list_sfx(session: SessionDep) -> list[SfxOut]:
    return session.scalars(select(SfxEntry).order_by(SfxEntry.source)).all()


@router.get("/sfx-glossary/missing")
def missing_sfx(session: SessionDep) -> list[SfxMissing]:
    """Reči onomatopeja iz projekata kojih nema u glosaru, sa predlogom po pravilu."""
    return sfx_glossary.missing(session)


@router.post("/sfx-glossary", status_code=status.HTTP_201_CREATED)
def create_sfx(data: SfxIn, session: SessionDep) -> SfxOut:
    entry = SfxEntry(source=_source(data.source), target=clean_term(data.target), note=data.note)
    session.add(entry)
    _commit(session)
    return entry


@router.patch("/sfx-glossary/{entry_id}")
def update_sfx(entry_id: int, data: SfxPatch, session: SessionDep) -> SfxOut:
    entry = _entry(session, entry_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "source" in changes:
        entry.source = _source(changes["source"])
    if "target" in changes:
        entry.target = clean_term(changes["target"])
    if "note" in changes:
        entry.note = changes["note"] or None
    _commit(session)
    return entry


@router.delete("/sfx-glossary/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sfx(entry_id: int, session: SessionDep) -> Response:
    session.delete(_entry(session, entry_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/sfx/apply")
def apply_sfx(project_id: int, session: SessionDep) -> SfxApplied:
    """Onomatopeje projekta ponovo po glosaru i pravilu (ručno izmenjene i odobrene ostaju)."""
    if session.get(Project, project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "projekat ne postoji")
    return SfxApplied(changed=sfx_glossary.apply_to_project(session, project_id))
