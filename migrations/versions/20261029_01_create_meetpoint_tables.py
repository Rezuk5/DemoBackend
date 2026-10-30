"""create meetpoint tables"""

import sqlalchemy as sa
from alembic import op

revision = "20261029_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_session_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_session_id"],
            ["sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("contact_type", sa.String(length=16), nullable=False),
        sa.Column("contact_value", sa.String(length=254), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("contact_type IN ('email', 'telegram')", name="ck_contact_type"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "session_id", name="uq_event_session"),
    )
    op.create_index(
        "ix_participant_feed", "participants", ["event_id", "created_at", "id"], unique=False
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "name", name="uq_event_tag"),
    )
    op.create_table(
        "connection_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'skipped')", name="ck_request_status"
        ),
        sa.CheckConstraint("sender_id <> recipient_id", name="ck_request_not_self"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["participants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_request_incoming",
        "connection_requests",
        ["event_id", "recipient_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_request_pair",
        "connection_requests",
        [
            "event_id",
            sa.literal_column("least(sender_id, recipient_id)"),
            sa.literal_column("greatest(sender_id, recipient_id)"),
        ],
        unique=True,
    )
    op.create_table(
        "participant_tags",
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("participant_id", "tag_id"),
    )


def downgrade():
    op.drop_table("participant_tags")
    op.drop_index("uq_request_pair", table_name="connection_requests")
    op.drop_index("ix_request_incoming", table_name="connection_requests")
    op.drop_table("connection_requests")
    op.drop_table("tags")
    op.drop_index("ix_participant_feed", table_name="participants")
    op.drop_table("participants")
    op.drop_table("events")
    op.drop_table("sessions")
