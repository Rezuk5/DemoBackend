import hashlib
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import COOKIE_NAME, get_settings
from app.db import get_db
from app.models import BrowserSession, Event, Participant

Db = Annotated[Session, Depends(get_db)]
session_cookie = APIKeyCookie(name=COOKIE_NAME, auto_error=False)


def check_origin(request: Request) -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin is not None and origin != get_settings().origin:
            raise HTTPException(403, "Запрос с другого сайта запрещён")


def find_session(db: Session, token: str | None) -> BrowserSession | None:
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    return db.scalar(
        select(BrowserSession).where(
            BrowserSession.token_hash == digest,
            BrowserSession.expires_at > datetime.now(UTC),
        )
    )


def get_current_session(
    db: Db, token: Annotated[str | None, Security(session_cookie)]
) -> BrowserSession:
    session = find_session(db, token)
    if session is None:
        raise HTTPException(401, "Создай сессию через POST /api/session")
    return session


CurrentSession = Annotated[BrowserSession, Depends(get_current_session)]


def get_event(db: Session, event_id: UUID) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "Мероприятие не найдено")
    return event


def get_current_participant(event_id: UUID, db: Db, session: CurrentSession) -> Participant:
    get_event(db, event_id)
    participant = db.scalar(
        select(Participant).where(
            Participant.event_id == event_id, Participant.session_id == session.id
        )
    )
    if participant is None:
        raise HTTPException(403, "Сначала заполни профиль на этом мероприятии")
    return participant


CurrentParticipant = Annotated[Participant, Depends(get_current_participant)]
