from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401
from app.config import get_settings
from app.db import Base

config = context.config
target_metadata = Base.metadata


def migrate(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif connection := config.attributes.get("connection"):
    migrate(connection)
else:
    engine = create_engine(get_settings().database_url.get_secret_value(), hide_parameters=True)
    with engine.connect() as connection:
        migrate(connection)
    engine.dispose()
