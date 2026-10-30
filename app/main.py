from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.dependencies import Db, check_origin
from app.routers import events, participants, requests, sessions

app = FastAPI(
    title="MeetPoint",
    version="0.1.0",
    description=(
        "Знакомства на мероприятиях. Начни с POST /api/session, затем создай мероприятие "
        "или заполни профиль. Контакты открываются только после принятого приглашения."
    ),
    dependencies=[Depends(check_origin)],
    responses={
        401: {"description": "Нет действующей сессии"},
        403: {"description": "Нет права на действие"},
        404: {"description": "Объект не найден"},
        409: {"description": "Конфликт состояния"},
    },
)
for router in (sessions.router, events.router, participants.router, requests.router):
    app.include_router(router, prefix="/api")


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/docs")


@app.get("/health", tags=["Сервис"], summary="Проверить приложение и БД")
def health(db: Db):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "База данных недоступна") from None
    return {"status": "ok"}
