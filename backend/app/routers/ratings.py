from collections import defaultdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import SessionDep
from app.models import TranslationRating, utcnow
from app.schemas import RatingCandidate, RatingItem, RatingScore, RatingStudy

router = APIRouter(prefix="/api/ratings", tags=["ratings"])


def _study(session, study: str) -> list[TranslationRating]:
    query = select(TranslationRating).where(TranslationRating.study == study)
    ratings = list(session.scalars(query.order_by(TranslationRating.item, TranslationRating.order)))
    if not ratings:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ocenjivanje ne postoji")
    return ratings


@router.get("/{study}")
def get_study(study: str, session: SessionDep) -> RatingStudy:
    """Svi blokovi uzorka sa kandidatima, bez podataka o tome koji je model napravio prevod."""
    grouped: dict[int, list[TranslationRating]] = defaultdict(list)
    for rating in _study(session, study):
        grouped[rating.item].append(rating)
    items = [
        RatingItem(
            item=item,
            page_position=candidates[0].page_position,
            block_position=candidates[0].block_position,
            source=candidates[0].source,
            candidates=[
                RatingCandidate.model_validate(c, from_attributes=True) for c in candidates
            ],
        )
        for item, candidates in sorted(grouped.items())
    ]
    rated = sum(all(c.score is not None for c in item.candidates) for item in items)
    return RatingStudy(study=study, total_items=len(items), rated_items=rated, items=items)


@router.put("/{study}/{rating_id}")
def rate(study: str, rating_id: int, data: RatingScore, session: SessionDep) -> RatingCandidate:
    rating = session.get(TranslationRating, rating_id)
    if rating is None or rating.study != study:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ocena ne postoji")
    rating.score = data.score
    rating.rated_at = utcnow()
    session.commit()
    return RatingCandidate.model_validate(rating, from_attributes=True)


@router.get("/{study}/summary")
def summary(study: str, session: SessionDep) -> dict:
    """Rezultat po kandidatu; dostupan tek kad su svi prevodi ocenjeni, da ocena ostane slepa."""
    ratings = _study(session, study)
    if any(rating.score is None for rating in ratings):
        raise HTTPException(status.HTTP_409_CONFLICT, "ocenjivanje još nije završeno")
    by_candidate: dict[str, list[int]] = defaultdict(list)
    for rating in ratings:
        by_candidate[rating.candidate].append(rating.score)
    return {
        "study": study,
        "candidates": [
            {
                "candidate": candidate,
                "average": sum(scores) / len(scores),
                "good_share": sum(score >= 4 for score in scores) / len(scores),
                "count": len(scores),
            }
            for candidate, scores in sorted(
                by_candidate.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])
            )
        ],
    }
