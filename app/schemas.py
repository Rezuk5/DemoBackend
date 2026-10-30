import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)


class Contact(Schema):
    type: Literal["telegram", "email"]
    value: str = Field(min_length=1, max_length=254)

    @model_validator(mode="after")
    def validate_contact(self):
        if self.type == "email":
            self.value = str(TypeAdapter(EmailStr).validate_python(self.value))
        else:
            username = self.value.removeprefix("@")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", username):
                raise ValueError("Укажи Telegram username длиной 5–32 символа")
            self.value = f"@{username}"
        return self


class EventCreate(Schema):
    name: str = Field(min_length=1, max_length=120)
    date: date
    description: str = Field(min_length=1, max_length=2000)
    tags: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(
        min_length=3, max_length=20
    )

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        names = [value.strip().lower() for value in values]
        if any(not name or len(name) > 40 for name in names):
            raise ValueError("Длина тега после нормализации должна быть от 1 до 40 символов")
        if len(set(names)) != len(names):
            raise ValueError("Теги мероприятия не должны повторяться")
        return names


class TagRead(Schema):
    id: int
    name: str


class EventRead(Schema):
    id: UUID
    name: str
    date: date
    description: str
    tags: list[TagRead]
    join_url: str
    qr_url: str


class ParticipantWrite(Schema):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Алиса",
                "role": "Backend developer",
                "tag_ids": [1, 2, 3],
                "contact": {"type": "telegram", "value": "@alice_demo"},
            }
        }
    )

    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=120)
    tag_ids: list[int] = Field(min_length=3, max_length=5)
    contact: Contact

    @field_validator("tag_ids")
    @classmethod
    def distinct_tags(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("Выбери разные теги")
        return values


class ParticipantPublic(Schema):
    id: UUID
    name: str
    role: str
    tags: list[TagRead]


class ParticipantSelf(ParticipantPublic):
    contact: Contact


class Recommendation(ParticipantPublic):
    common_tags_count: int


class ContactRead(ParticipantSelf):
    pass


class RequestCreate(Schema):
    recipient_id: UUID


class RequestDecision(Schema):
    status: Literal["accepted", "skipped"]


class RequestRead(Schema):
    id: UUID
    sender: ParticipantPublic
    recipient_id: UUID
    status: Literal["pending", "accepted", "skipped"]
    created_at: datetime
    responded_at: datetime | None


class Page[T](Schema):
    items: list[T]
    limit: int
    offset: int


class Pagination(Schema):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class EventStats(Schema):
    participants_count: int
    requests_sent: int
    requests_accepted: int
    connections_count: int
