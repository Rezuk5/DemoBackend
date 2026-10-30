from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import CurrentParticipant, Db
from app.models import ConnectionRequest
from app.routers.participants import Paging
from app.schemas import Page, RequestCreate, RequestDecision, RequestRead
from app.services import respond_to_request, send_request

router = APIRouter(tags=["Знакомства"])


@router.post(
    "/events/{event_id}/requests",
    response_model=RequestRead,
    status_code=201,
    summary="Хочу познакомиться",
)
def invite(data: RequestCreate, db: Db, me: CurrentParticipant):
    return send_request(db, me, data.recipient_id)


@router.get(
    "/events/{event_id}/requests", response_model=Page[RequestRead], summary="Входящие запросы"
)
def incoming(
    db: Db,
    me: CurrentParticipant,
    page: Paging,
    status: Literal["pending", "accepted", "skipped"] = "pending",
):
    invitations = db.scalars(
        select(ConnectionRequest)
        .where(
            ConnectionRequest.event_id == me.event_id,
            ConnectionRequest.recipient_id == me.id,
            ConnectionRequest.status == status,
        )
        .order_by(ConnectionRequest.created_at, ConnectionRequest.id)
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return Page[RequestRead](items=invitations, **page.model_dump())


@router.patch(
    "/events/{event_id}/requests/{request_id}",
    response_model=RequestRead,
    summary="Принять или пропустить запрос",
)
def decide(request_id: UUID, data: RequestDecision, db: Db, me: CurrentParticipant):
    """Решение окончательное. Повтор того же ответа допустим; изменить его нельзя."""
    return respond_to_request(db, me, request_id, data.status)
