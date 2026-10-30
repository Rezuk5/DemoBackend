"""Create one repeatable demo event; store its sessions in ignored cookie files."""

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.config import COOKIE_NAME, get_settings
from app.db import get_engine
from app.models import BrowserSession, Event, Tag
from app.schemas import Contact, ParticipantWrite
from app.services import join_event

DEMO_ID = uuid5(NAMESPACE_URL, "meetpoint/demo/event")
COOKIE_DIR = Path(".local/demo")
PEOPLE = [
    ("alice", "Алиса", "Backend developer", [0, 1, 4]),
    ("bob", "Борис", "ML engineer", [0, 4, 5]),
    ("claire", "Клара", "Product designer", [2, 3, 5]),
    ("dan", "Даниил", "Frontend developer", [0, 2, 3]),
]


def demo_session(db: Session, label: str) -> BrowserSession:
    settings = get_settings()
    session_id = uuid5(DEMO_ID, label)
    session = db.get(BrowserSession, session_id)
    if session is None:
        session = BrowserSession(id=session_id)
        db.add(session)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=settings.session_days)
    session.token_hash = hashlib.sha256(token.encode()).hexdigest()
    session.expires_at = expires
    db.commit()

    # A cookie jar works with curl without putting a session token in shell history.
    hostname = urlsplit(settings.origin).hostname
    secure = "TRUE" if settings.secure_cookie else "FALSE"
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    (COOKIE_DIR / f"{label}.cookies").write_text(
        "# Netscape HTTP Cookie File\n"
        f"{hostname}\tFALSE\t/\t{secure}\t{int(expires.timestamp())}\t{COOKIE_NAME}\t{token}\n",
        encoding="utf-8",
    )
    return session


def main() -> None:
    with Session(get_engine(), expire_on_commit=False) as db:
        owner = demo_session(db, "organizer")
        event = db.get(Event, DEMO_ID)
        if event is None:
            event = Event(
                id=DEMO_ID,
                owner_session_id=owner.id,
                name="MeetPoint · встреча разработчиков",
                date=date(2026, 11, 1),
                description="Найди людей с общими интересами и обменяйся контактами по согласию.",
                tags=[
                    Tag(name=name)
                    for name in ["python", "postgresql", "frontend", "design", "ml", "career"]
                ],
            )
            db.add(event)
            db.commit()
        tag_ids = [tag.id for tag in event.tags]
        for label, name, role, indexes in PEOPLE:
            actor = demo_session(db, label)
            join_event(
                db,
                event.id,
                actor.id,
                ParticipantWrite(
                    name=name,
                    role=role,
                    tag_ids=[tag_ids[index] for index in indexes],
                    contact=Contact(type="telegram", value=f"@{label}_meetpoint_demo"),
                ),
            )
    print(f"Event: {get_settings().origin}/api/events/{DEMO_ID}")
    print(f"Demo cookies: {COOKIE_DIR.resolve()}")


if __name__ == "__main__":
    main()
