from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

participant_tags = Table(
    "participant_tags",
    Base.metadata,
    Column("participant_id", ForeignKey("participants.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class BrowserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"))
    name: Mapped[str] = mapped_column(String(120))
    date: Mapped[date]
    description: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tags: Mapped[list[Tag]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="Tag.id"
    )


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("event_id", "name", name="uq_event_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(40))


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("event_id", "session_id", name="uq_event_session"),
        CheckConstraint("contact_type IN ('email', 'telegram')", name="ck_contact_type"),
        Index("ix_participant_feed", "event_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"))
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(120))
    contact_type: Mapped[str] = mapped_column(String(16))
    contact_value: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tags: Mapped[list[Tag]] = relationship(
        secondary=participant_tags, lazy="selectin", order_by="Tag.id"
    )


class ConnectionRequest(Base):
    __tablename__ = "connection_requests"
    __table_args__ = (
        CheckConstraint("sender_id <> recipient_id", name="ck_request_not_self"),
        CheckConstraint("status IN ('pending', 'accepted', 'skipped')", name="ck_request_status"),
        Index("ix_request_incoming", "event_id", "recipient_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sender: Mapped[Participant] = relationship(foreign_keys=[sender_id], lazy="selectin")


# Sorting the two IDs also prevents simultaneous invitations in opposite directions.
Index(
    "uq_request_pair",
    ConnectionRequest.event_id,
    func.least(ConnectionRequest.sender_id, ConnectionRequest.recipient_id),
    func.greatest(ConnectionRequest.sender_id, ConnectionRequest.recipient_id),
    unique=True,
)
