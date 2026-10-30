from io import BytesIO
from uuid import UUID

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import func, select

from app.config import get_settings
from app.dependencies import CurrentSession, Db, get_event
from app.models import ConnectionRequest, Event, Participant, Tag
from app.schemas import EventCreate, EventRead, EventStats

router = APIRouter(tags=["Мероприятия"])


def event_info(event: Event) -> EventRead:
    origin = get_settings().origin
    return EventRead(
        id=event.id,
        name=event.name,
        date=event.date,
        description=event.description,
        tags=event.tags,
        join_url=f"{origin}/api/events/{event.id}",
        qr_url=f"{origin}/api/events/{event.id}/qr.svg",
    )


@router.post("/events", response_model=EventRead, status_code=201, summary="Создать мероприятие")
def create_event(data: EventCreate, db: Db, session: CurrentSession):
    event = Event(
        owner_session_id=session.id,
        name=data.name,
        date=data.date,
        description=data.description,
        tags=[Tag(name=name) for name in data.tags],
    )
    db.add(event)
    db.commit()
    return event_info(event)


@router.get("/events/{event_id}", response_model=EventRead, summary="Информация о мероприятии")
def read_event(event_id: UUID, db: Db):
    return event_info(get_event(db, event_id))


@router.get(
    "/events/{event_id}/qr.svg",
    summary="QR со ссылкой на мероприятие",
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}}}},
)
def event_qr(event_id: UUID, db: Db):
    image = qrcode.make(
        event_info(get_event(db, event_id)).join_url,
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    output = BytesIO()
    image.save(output)
    return Response(output.getvalue(), media_type="image/svg+xml")


@router.get(
    "/events/{event_id}/stats", response_model=EventStats, summary="Статистика организатора"
)
def event_stats(event_id: UUID, db: Db, session: CurrentSession):
    if get_event(db, event_id).owner_session_id != session.id:
        raise HTTPException(403, "Статистика доступна только организатору")
    participants = db.scalar(
        select(func.count(Participant.id)).where(Participant.event_id == event_id)
    )
    sent, accepted = db.execute(
        select(
            func.count(ConnectionRequest.id),
            func.count(ConnectionRequest.id).filter(ConnectionRequest.status == "accepted"),
        ).where(ConnectionRequest.event_id == event_id)
    ).one()
    return EventStats(
        participants_count=participants,
        requests_sent=sent,
        requests_accepted=accepted,
        connections_count=accepted,
    )
