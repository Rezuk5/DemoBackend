from app.config import COOKIE_NAME
from tests.helpers import assert_public, together


def invite(pair):
    response = pair.alice.post(
        f"{pair.path}/requests", json={"recipient_id": pair.bob_profile["id"]}
    )
    assert response.status_code == 201, response.text
    assert_public(response.json())
    return response.json()


def test_contacts_open_for_both_sides_only_after_acceptance(pair):
    invitation = invite(pair)
    for client in (pair.alice, pair.bob):
        for suffix in ("participants", "recommendations", "requests"):
            response = client.get(f"{pair.path}/{suffix}")
            assert response.status_code == 200, response.text
            assert_public(response.json())
            assert response.headers["cache-control"] == "no-store"
        assert client.get(f"{pair.path}/contacts").json()["items"] == []
    assert len(pair.bob.get(f"{pair.path}/requests").json()["items"]) == 1

    path = f"{pair.path}/requests/{invitation['id']}"
    accepted = pair.bob.patch(path, json={"status": "accepted"})
    assert accepted.status_code == 200, accepted.text
    assert_public(accepted.json())
    assert accepted.json()["responded_at"] is not None
    assert pair.bob.patch(path, json={"status": "accepted"}).status_code == 200
    assert pair.bob.patch(path, json={"status": "skipped"}).status_code == 409
    for client, expected in [(pair.alice, pair.bob_profile), (pair.bob, pair.alice_profile)]:
        contacts = client.get(f"{pair.path}/contacts")
        assert contacts.status_code == 200, contacts.text
        assert contacts.json()["items"] == [expected]
    assert pair.owner.get(f"{pair.path}/stats").json() == {
        "participants_count": 2,
        "requests_sent": 1,
        "requests_accepted": 1,
        "connections_count": 1,
    }


def test_skipping_is_final_and_never_reveals_contacts(pair):
    invitation = invite(pair)
    path = f"{pair.path}/requests/{invitation['id']}"
    assert pair.bob.patch(path, json={"status": "skipped"}).status_code == 200
    assert pair.bob.patch(path, json={"status": "skipped"}).status_code == 200
    assert pair.bob.patch(path, json={"status": "accepted"}).status_code == 409
    for client in (pair.alice, pair.bob):
        assert client.get(f"{pair.path}/contacts").json()["items"] == []
    skipped = pair.bob.get(f"{pair.path}/requests", params={"status": "skipped"})
    assert skipped.status_code == 200
    assert_public(skipped.json())
    assert len(skipped.json()["items"]) == 1
    assert pair.owner.get(f"{pair.path}/stats").json()["connections_count"] == 0


def test_self_duplicate_and_reverse_invitations_are_rejected(pair):
    assert (
        pair.alice.post(
            f"{pair.path}/requests", json={"recipient_id": pair.alice_profile["id"]}
        ).status_code
        == 409
    )
    invite(pair)
    for client, target in [(pair.alice, pair.bob_profile), (pair.bob, pair.alice_profile)]:
        response = client.post(f"{pair.path}/requests", json={"recipient_id": target["id"]})
        assert response.status_code == 409
    assert pair.owner.get(f"{pair.path}/stats").json()["requests_sent"] == 1


def test_only_recipient_can_decide_and_sender_cannot_be_forged(pair, client_factory, join):
    invitation = invite(pair)
    stranger = client_factory()
    join(stranger, pair.event, "Charlie")
    for client in (pair.alice, stranger):
        assert (
            client.patch(
                f"{pair.path}/requests/{invitation['id']}", json={"status": "accepted"}
            ).status_code
            == 403
        )
    assert (
        pair.alice.post(
            f"{pair.path}/requests",
            json={"recipient_id": pair.bob_profile["id"], "sender_id": "someone-else"},
        ).status_code
        == 422
    )
    assert pair.bob.get(f"{pair.path}/requests").json()["items"][0]["status"] == "pending"


def test_parallel_invitations_create_one_pair(pair, client_factory):
    alice = client_factory(cookie=pair.alice.cookies.get(COOKIE_NAME))
    bob = client_factory(cookie=pair.bob.cookies.get(COOKIE_NAME))
    responses = together(
        lambda: alice.post(f"{pair.path}/requests", json={"recipient_id": pair.bob_profile["id"]}),
        lambda: bob.post(f"{pair.path}/requests", json={"recipient_id": pair.alice_profile["id"]}),
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert pair.owner.get(f"{pair.path}/stats").json()["requests_sent"] == 1


def test_parallel_opposite_decisions_have_one_winner(pair, client_factory):
    invitation = invite(pair)
    clients = [client_factory(cookie=pair.bob.cookies.get(COOKIE_NAME)) for _ in range(2)]
    path = f"{pair.path}/requests/{invitation['id']}"
    responses = together(
        lambda: clients[0].patch(path, json={"status": "accepted"}),
        lambda: clients[1].patch(path, json={"status": "skipped"}),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(
        response.json()["status"] for response in responses if response.status_code == 200
    )
    count = int(winner == "accepted")
    assert len(pair.alice.get(f"{pair.path}/contacts").json()["items"]) == count
    assert len(pair.bob.get(f"{pair.path}/contacts").json()["items"]) == count
    assert pair.owner.get(f"{pair.path}/stats").json()["connections_count"] == count
