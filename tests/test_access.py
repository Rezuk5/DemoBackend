import hashlib
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import COOKIE_NAME, get_settings
from app.models import BrowserSession
from tests.helpers import assert_public, event_data, profile_data


def test_membership_and_organizer_permissions(pair, client_factory, join):
    anonymous = client_factory(start_session=False)
    assert anonymous.get(pair.path).status_code == 200
    assert anonymous.get(f"{pair.path}/participants").status_code == 401
    assert anonymous.post("/api/events", json=event_data()).status_code == 401
    for suffix in ("participants", "recommendations", "requests", "contacts", "me"):
        assert pair.owner.get(f"{pair.path}/{suffix}").status_code == 403
    assert pair.alice.get(f"{pair.path}/stats").status_code == 403
    outsider = client_factory()
    join(outsider, pair.event, "Charlie")
    assert outsider.get(f"{pair.path}/contacts").json()["items"] == []
    assert_public(pair.owner.get(f"{pair.path}/stats").json())


def test_event_boundaries_apply_to_tags_people_requests_and_contacts(pair, join):
    other = pair.owner.post("/api/events", json=event_data(name="Other meetup")).json()
    other_path = f"/api/events/{other['id']}"
    join(pair.alice, other)
    other_bob = join(pair.bob, other, "Bob")
    assert (
        pair.alice.post(
            f"{other_path}/requests", json={"recipient_id": pair.bob_profile["id"]}
        ).status_code
        == 404
    )
    assert pair.alice.put(f"{other_path}/me", json=profile_data(pair.event)).status_code == 422
    assert (
        pair.alice.get(
            f"{other_path}/participants", params={"tag_ids": pair.event["tags"][0]["id"]}
        ).status_code
        == 422
    )
    feed = pair.alice.get(f"{other_path}/participants").json()["items"]
    assert [person["id"] for person in feed] == [other_bob["id"]]

    invitation = pair.alice.post(
        f"{pair.path}/requests", json={"recipient_id": pair.bob_profile["id"]}
    ).json()
    assert (
        pair.bob.patch(
            f"{other_path}/requests/{invitation['id']}", json={"status": "accepted"}
        ).status_code
        == 404
    )
    assert pair.bob.get(f"{other_path}/requests").json()["items"] == []
    assert (
        pair.bob.patch(
            f"{pair.path}/requests/{invitation['id']}", json={"status": "accepted"}
        ).status_code
        == 200
    )
    assert pair.alice.get(f"{other_path}/contacts").json()["items"] == []
    assert pair.bob.get(f"{other_path}/contacts").json()["items"] == []


def test_expired_session_cannot_recover_profile_or_organizer_rights(event, db_engine):
    owner, meetup = event
    old_token = owner.cookies.get(COOKIE_NAME)
    with Session(db_engine) as db:
        db.execute(
            update(BrowserSession)
            .where(BrowserSession.token_hash == hashlib.sha256(old_token.encode()).hexdigest())
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()
    path = f"/api/events/{meetup['id']}"
    assert owner.get(f"{path}/stats").status_code == 401
    assert owner.post("/api/session").status_code == 200
    assert owner.cookies.get(COOKIE_NAME) != old_token
    assert owner.get(f"{path}/stats").status_code == 403


def test_foreign_origin_is_rejected_before_session_creation(client_factory, db_engine):
    client = client_factory(start_session=False)
    for origin in ("https://other.example", "null"):
        response = client.post("/api/session", headers={"Origin": origin})
        assert response.status_code == 403
        assert COOKIE_NAME not in client.cookies
    with Session(db_engine) as db:
        assert db.scalar(select(func.count(BrowserSession.id))) == 0
    response = client.post("/api/session", headers={"Origin": get_settings().origin})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.post(
            "/api/events", headers={"Origin": "https://other.example"}, json=event_data()
        ).status_code
        == 403
    )


def test_public_event_and_qr_do_not_expose_private_state(client_factory):
    owner = client_factory()
    response = owner.post("/api/events", json=event_data(name="<script>alert(1)</script>"))
    assert response.status_code == 201, response.text
    meetup = response.json()
    assert_public(meetup)
    visitor = client_factory(start_session=False)
    assert meetup["join_url"] == f"{get_settings().origin}/api/events/{meetup['id']}"
    event = visitor.get(meetup["join_url"])
    assert event.status_code == 200
    assert event.headers["content-type"].startswith("application/json")
    assert event.json() == meetup
    assert visitor.get(f"/events/{meetup['id']}").status_code == 404
    qr = visitor.get(meetup["qr_url"])
    assert qr.status_code == 200
    assert qr.headers["content-type"].startswith("image/svg+xml")
    assert ElementTree.fromstring(qr.content).tag.endswith("svg")
