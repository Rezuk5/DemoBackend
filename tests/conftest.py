import os
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import COOKIE_NAME, get_settings
from app.db import Base, get_db
from app.main import app
from tests.helpers import event_data, profile_data


@pytest.fixture(scope="session")
def db_engine():
    test_dsn = os.environ.get("TEST_DATABASE_URL")
    if not test_dsn:
        raise pytest.UsageError("Задай TEST_DATABASE_URL для отдельной PostgreSQL БД *_test")
    test_url = make_url(test_dsn)
    app_url = make_url(get_settings().database_url.get_secret_value())
    if (
        test_url.get_backend_name() != "postgresql"
        or not test_url.database
        or not test_url.database.endswith("_test")
        or test_url.database == app_url.database
    ):
        raise pytest.UsageError("Тесты разрешены только в отдельной PostgreSQL БД *_test")
    engine = create_engine(test_url, hide_parameters=True, pool_pre_ping=True)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(db_engine):
    def clear():
        with db_engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(delete(table))

    clear()
    yield
    clear()


@pytest.fixture
def client_factory(db_engine):
    def test_db():
        with Session(db_engine, expire_on_commit=False) as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = test_db
    with ExitStack() as clients:

        def factory(*, cookie=None, start_session=True):
            client = clients.enter_context(TestClient(app, base_url=get_settings().origin))
            if cookie:
                client.cookies.set(COOKIE_NAME, cookie)
            elif start_session:
                response = client.post("/api/session")
                assert response.status_code == 200, response.text
            return client

        yield factory
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def event(client_factory):
    owner = client_factory()
    response = owner.post("/api/events", json=event_data())
    assert response.status_code == 201, response.text
    return owner, response.json()


@pytest.fixture
def join():
    def create(client, event, name="Alice", indexes=(0, 1, 2), **changes):
        response = client.put(
            f"/api/events/{event['id']}/me",
            json=profile_data(event, name, indexes, **changes),
        )
        assert response.status_code == 200, response.text
        return response.json()

    return create


@dataclass
class Pair:
    owner: TestClient
    event: dict
    alice: TestClient
    bob: TestClient
    alice_profile: dict
    bob_profile: dict

    @property
    def path(self):
        return f"/api/events/{self.event['id']}"


@pytest.fixture
def pair(event, client_factory, join):
    owner, meetup = event
    alice, bob = client_factory(), client_factory()
    return Pair(owner, meetup, alice, bob, join(alice, meetup), join(bob, meetup, "Bob"))
