from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Participant
from tests.helpers import assert_public


def test_recommendations_rank_before_pagination_and_keep_stable_ties(
    event, client_factory, join, db_engine
):
    _, meetup = event
    me = client_factory()
    own = join(me, meetup)
    zero = join(client_factory(), meetup, "Zero", indexes=(3, 4, 5))
    tied = [
        join(client_factory(), meetup, "First", indexes=(0, 1, 3)),
        join(client_factory(), meetup, "Second", indexes=(0, 1, 4)),
    ]
    best = join(client_factory(), meetup, "Best")
    with Session(db_engine) as db:
        db.execute(
            update(Participant)
            .where(Participant.id.in_([UUID(person["id"]) for person in tied]))
            .values(created_at=datetime(2026, 10, 29, tzinfo=UTC))
        )
        db.commit()
    expected = [best["id"], *sorted(person["id"] for person in tied), zero["id"]]
    path = f"/api/events/{meetup['id']}/recommendations"
    response = me.get(path)
    assert response.status_code == 200, response.text
    data = response.json()
    assert_public(data)
    assert [person["id"] for person in data["items"]] == expected
    assert [person["common_tags_count"] for person in data["items"]] == [3, 2, 2, 0]
    assert own["id"] not in expected
    for offset, person_id in enumerate(expected):
        paged = me.get(path, params={"limit": 1, "offset": offset}).json()
        assert [person["id"] for person in paged["items"]] == [person_id]
    assert me.get(path, params={"offset": 100}).json()["items"] == []


def test_tag_filter_uses_any_selected_tag_and_validates_pagination(event, client_factory, join):
    _, meetup = event
    me = client_factory()
    join(me, meetup)
    left = join(client_factory(), meetup, "Left", indexes=(0, 2, 3))
    right = join(client_factory(), meetup, "Right", indexes=(1, 2, 4))
    join(client_factory(), meetup, "Neither", indexes=(2, 3, 4))
    path = f"/api/events/{meetup['id']}/participants"
    response = me.get(path, params=[("tag_ids", tag["id"]) for tag in meetup["tags"][:2]])
    assert response.status_code == 200, response.text
    assert {person["id"] for person in response.json()["items"]} == {left["id"], right["id"]}
    assert_public(response.json())
    assert me.get(path, params={"tag_ids": meetup["tags"][5]["id"]}).json()["items"] == []
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert me.get(path, params=params).status_code == 422
