from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import COOKIE_NAME
from app.models import BrowserSession, Participant
from tests.helpers import event_data, profile_data, together


def test_session_and_profile_survive_repeated_entry(event, client_factory, join, db_engine):
    _, meetup = event
    client = client_factory()
    token = client.cookies.get(COOKIE_NAME)
    first = join(client, meetup)
    assert client.post("/api/session").status_code == 200
    assert client.cookies.get(COOKIE_NAME) == token
    updated = join(client, meetup, "Alice", indexes=(1, 2, 3))
    assert first["id"] == updated["id"]
    assert {tag["id"] for tag in updated["tags"]} == {
        meetup["tags"][index]["id"] for index in (1, 2, 3)
    }
    assert client.get(f"/api/events/{meetup['id']}/me").json() == updated
    with Session(db_engine) as db:
        assert db.scalar(select(func.count(Participant.id))) == 1
        assert db.scalar(select(func.count(BrowserSession.id))) == 2


def test_invalid_profile_does_not_overwrite_existing_one(pair):
    payload = profile_data(pair.event)
    invalid_values = [
        {"name": "   "},
        {"tag_ids": payload["tag_ids"][:2]},
        {"tag_ids": [payload["tag_ids"][0]] * 3},
        {"tag_ids": [*payload["tag_ids"][:2], 999999]},
        {"contact": {"type": "email", "value": "not-an-email"}},
        {"contact": {"type": "telegram", "value": "@@bad"}},
        {"session_id": "client-cannot-choose-identity"},
    ]
    for changes in invalid_values:
        response = pair.alice.put(f"{pair.path}/me", json={**payload, **changes})
        assert response.status_code == 422, response.text
        assert pair.alice.get(f"{pair.path}/me").json() == pair.alice_profile


def test_event_tags_are_normalized_and_duplicates_rejected(client_factory):
    owner = client_factory()
    response = owner.post("/api/events", json=event_data(tags=[" Python ", "POSTGRES", "design"]))
    assert response.status_code == 201, response.text
    assert [tag["name"] for tag in response.json()["tags"]] == ["python", "postgres", "design"]
    duplicate = owner.post("/api/events", json=event_data(tags=[" Python ", "PYTHON", "design"]))
    assert duplicate.status_code == 422
    expanded = owner.post("/api/events", json=event_data(tags=["İ" * 40, "python", "design"]))
    assert expanded.status_code == 422


def test_parallel_registration_keeps_one_profile_and_complete_tag_set(
    event, client_factory, db_engine
):
    _, meetup = event
    client = client_factory()
    copies = [client_factory(cookie=client.cookies.get(COOKIE_NAME)) for _ in range(2)]
    payloads = [profile_data(meetup, indexes=indexes) for indexes in [(0, 1, 2), (3, 4, 5)]]
    responses = together(
        lambda: copies[0].put(f"/api/events/{meetup['id']}/me", json=payloads[0]),
        lambda: copies[1].put(f"/api/events/{meetup['id']}/me", json=payloads[1]),
    )
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    saved = client.get(f"/api/events/{meetup['id']}/me").json()
    assert {tag["id"] for tag in saved["tags"]} in [set(p["tag_ids"]) for p in payloads]
    with Session(db_engine) as db:
        assert db.scalar(select(func.count(Participant.id))) == 1
