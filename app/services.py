from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, delete, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ConnectionRequest, Participant, Tag, participant_tags
from app.schemas import Contact, ParticipantSelf, ParticipantWrite


def profile_with_contact(participant: Participant) -> ParticipantSelf:
    return ParticipantSelf(
        id=participant.id,
        name=participant.name,
        role=participant.role,
        tags=participant.tags,
        contact=Contact(type=participant.contact_type, value=participant.contact_value),
    )


def validate_tags(db: Session, event_id: UUID, tag_ids: list[int]) -> None:
    count = db.scalar(
        select(func.count(Tag.id)).where(Tag.event_id == event_id, Tag.id.in_(set(tag_ids)))
    )
    if count != len(set(tag_ids)):
        raise HTTPException(422, "Все теги должны принадлежать этому мероприятию")


def join_event(
    db: Session, event_id: UUID, session_id: UUID, data: ParticipantWrite
) -> Participant:
    validate_tags(db, event_id, data.tag_ids)
    values = {
        "name": data.name,
        "role": data.role,
        "contact_type": data.contact.type,
        "contact_value": data.contact.value,
    }
    # Upsert locks this profile until commit, including replacement of its tags.
    participant_id = db.scalar(
        pg_insert(Participant)
        .values(event_id=event_id, session_id=session_id, **values)
        .on_conflict_do_update(constraint="uq_event_session", set_=values)
        .returning(Participant.id)
    )
    db.execute(delete(participant_tags).where(participant_tags.c.participant_id == participant_id))
    db.execute(
        insert(participant_tags),
        [{"participant_id": participant_id, "tag_id": tag_id} for tag_id in sorted(data.tag_ids)],
    )
    db.commit()
    db.expire_all()
    return db.get(Participant, participant_id)


def recommend(db: Session, me: Participant, limit: int, offset: int):
    my_tags = select(participant_tags.c.tag_id).where(participant_tags.c.participant_id == me.id)
    common_tags = (
        select(participant_tags.c.participant_id, func.count().label("count"))
        .where(participant_tags.c.tag_id.in_(my_tags))
        .group_by(participant_tags.c.participant_id)
        .subquery()
    )
    score = func.coalesce(common_tags.c.count, 0)
    return db.execute(
        select(Participant, score)
        .outerjoin(common_tags, Participant.id == common_tags.c.participant_id)
        .where(Participant.event_id == me.event_id, Participant.id != me.id)
        .order_by(score.desc(), Participant.created_at, Participant.id)
        .limit(limit)
        .offset(offset)
    ).all()


def send_request(db: Session, me: Participant, recipient_id: UUID) -> ConnectionRequest:
    if recipient_id == me.id:
        raise HTTPException(409, "Нельзя отправить запрос самому себе")
    recipient = db.scalar(
        select(Participant).where(
            Participant.id == recipient_id, Participant.event_id == me.event_id
        )
    )
    if recipient is None:
        raise HTTPException(404, "Участник не найден на этом мероприятии")
    invitation = ConnectionRequest(event_id=me.event_id, sender_id=me.id, recipient_id=recipient_id)
    db.add(invitation)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if getattr(error.orig.diag, "constraint_name", None) == "uq_request_pair":
            raise HTTPException(409, "Между вами уже есть запрос на знакомство") from None
        raise
    db.refresh(invitation)
    return invitation


def respond_to_request(
    db: Session, me: Participant, request_id: UUID, decision: str
) -> ConnectionRequest:
    invitation = db.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.id == request_id, ConnectionRequest.event_id == me.event_id
        )
    )
    if invitation is None:
        raise HTTPException(404, "Запрос не найден на этом мероприятии")
    if invitation.recipient_id != me.id:
        raise HTTPException(403, "Ответить может только получатель")

    changed = db.scalar(
        update(ConnectionRequest)
        .where(ConnectionRequest.id == request_id, ConnectionRequest.status == "pending")
        .values(status=decision, responded_at=datetime.now(UTC))
        .returning(ConnectionRequest.id)
        .execution_options(synchronize_session=False)
    )
    if changed is not None:
        db.commit()
    db.refresh(invitation)
    if invitation.status != decision:
        raise HTTPException(409, "По этому запросу уже принято другое решение")
    return invitation


def get_contacts(db: Session, me: Participant, limit: int, offset: int) -> list[Participant]:
    peer_id = case(
        (ConnectionRequest.sender_id == me.id, ConnectionRequest.recipient_id),
        else_=ConnectionRequest.sender_id,
    )
    return list(
        db.scalars(
            select(Participant)
            .join(ConnectionRequest, Participant.id == peer_id)
            .where(
                ConnectionRequest.event_id == me.event_id,
                ConnectionRequest.status == "accepted",
                Participant.event_id == me.event_id,
                or_(ConnectionRequest.sender_id == me.id, ConnectionRequest.recipient_id == me.id),
            )
            .order_by(Participant.name, Participant.id)
            .limit(limit)
            .offset(offset)
        )
    )
