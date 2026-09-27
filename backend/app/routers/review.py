"""Lektura: upozorenja po stranici i korisnikov rečnik."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import SessionDep
from app.models import DictionaryWord, Series
from app.routers.pages import get_page
from app.schemas import BlockReviewOut, DictionaryIn, DictionaryOut, PageReviewOut
from app.services.review import review_page

router = APIRouter(prefix="/api", tags=["review"])


@router.get("/pages/{page_id}/review")
def page_review(page_id: int, session: SessionDep) -> PageReviewOut:
    page = get_page(session, page_id)
    return PageReviewOut(
        page_id=page.id,
        reviewed=page.translation_reviewed,
        blocks=[BlockReviewOut.model_validate(item) for item in review_page(session, page)],
    )


@router.get("/series/{series_id}/dictionary")
def list_dictionary(series_id: int, session: SessionDep) -> list[DictionaryOut]:
    if session.get(Series, series_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serijal ne postoji")
    query = select(DictionaryWord).where(DictionaryWord.series_id == series_id)
    return list(session.scalars(query.order_by(DictionaryWord.word)))


@router.post("/series/{series_id}/dictionary", status_code=status.HTTP_201_CREATED)
def add_word(series_id: int, data: DictionaryIn, session: SessionDep) -> DictionaryOut:
    if session.get(Series, series_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serijal ne postoji")
    word = DictionaryWord(series_id=series_id, word=data.word.strip().lower())
    session.add(word)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(DictionaryWord).where(
                DictionaryWord.series_id == series_id,
                DictionaryWord.word == data.word.strip().lower(),
            )
        )
        return existing  # ista reč dva puta nije greška
    return word


@router.delete("/dictionary/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_word(word_id: int, session: SessionDep) -> Response:
    word = session.get(DictionaryWord, word_id)
    if word is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reč ne postoji")
    session.delete(word)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
