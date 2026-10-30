from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.dependencies import CurrentParticipant, CurrentSession, Db, get_event
from app.models import Participant, Tag
from app.schemas import (
    ContactRead,
    Page,
    Pagination,
    ParticipantPublic,
    ParticipantSelf,
    ParticipantWrite,
    Recommendation,
)
from app.services import get_contacts, join_event, profile_with_contact, recommend, validate_tags

router = APIRouter(tags=["Участники"])
Paging = Annotated[Pagination, Depends()]


@router.put(
    "/events/{event_id}/me",
    response_model=ParticipantSelf,
    summary="Заполнить или обновить профиль",
)
def save_profile(event_id: UUID, data: ParticipantWrite, db: Db, session: CurrentSession):
    """Выбери 3–5 ID тегов из информации о мероприятии. Повторный вызов обновит тот же профиль."""
    get_event(db, event_id)
    return profile_with_contact(join_event(db, event_id, session.id, data))


@router.get("/events/{event_id}/me", response_model=ParticipantSelf, summary="Мой профиль")
def read_profile(me: CurrentParticipant):
    return profile_with_contact(me)


@router.get(
    "/events/{event_id}/participants",
    response_model=Page[ParticipantPublic],
    summary="Лента участников",
)
def list_participants(
    db: Db,
    me: CurrentParticipant,
    page: Paging,
    tag_ids: Annotated[list[int] | None, Query(description="Хотя бы один из этих тегов")] = None,
):
    query = select(Participant).where(Participant.event_id == me.event_id, Participant.id != me.id)
    if tag_ids:
        validate_tags(db, me.event_id, tag_ids)
        query = query.where(Participant.tags.any(Tag.id.in_(tag_ids)))
    people = db.scalars(
        query.order_by(Participant.created_at, Participant.id).limit(page.limit).offset(page.offset)
    ).all()
    return Page[ParticipantPublic](items=people, **page.model_dump())


@router.get(
    "/events/{event_id}/recommendations",
    response_model=Page[Recommendation],
    summary="Люди с общими интересами",
)
def recommendations(db: Db, me: CurrentParticipant, page: Paging):
    people = [
        Recommendation(
            **ParticipantPublic.model_validate(person).model_dump(), common_tags_count=score
        )
        for person, score in recommend(db, me, page.limit, page.offset)
    ]
    return Page[Recommendation](items=people, **page.model_dump())


@router.get("/events/{event_id}/contacts", response_model=Page[ContactRead], summary="Мои контакты")
def contacts(db: Db, me: CurrentParticipant, page: Paging):
    people = [
        profile_with_contact(person) for person in get_contacts(db, me, page.limit, page.offset)
    ]
    return Page[ContactRead](items=people, **page.model_dump())
