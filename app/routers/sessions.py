import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response

from app.config import COOKIE_NAME, get_settings
from app.dependencies import Db, find_session
from app.models import BrowserSession

router = APIRouter(tags=["Сессия"])


@router.post("/session", summary="Начать или продолжить сессию")
def start_session(request: Request, response: Response, db: Db) -> dict[str, str]:
    """Вызови один раз перед работой. Браузер сохранит cookie автоматически."""
    if find_session(db, request.cookies.get(COOKIE_NAME)) is not None:
        return {"status": "ok"}
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    lifetime = timedelta(days=settings.session_days)
    db.add(
        BrowserSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + lifetime,
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookie,
        path="/",
    )
    return {"status": "ok"}
