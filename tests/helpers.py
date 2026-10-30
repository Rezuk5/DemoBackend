from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


def event_data(**changes):
    return {
        "name": "Backend meetup",
        "date": "2026-11-01",
        "description": "Meet people who build things.",
        "tags": ["python", "postgres", "design", "ml", "career", "frontend"],
        **changes,
    }


def profile_data(event, name="Alice", indexes=(0, 1, 2), **changes):
    return {
        "name": name,
        "role": "Developer",
        "tag_ids": [event["tags"][index]["id"] for index in indexes],
        "contact": {"type": "telegram", "value": f"@{name.lower()}_demo"},
        **changes,
    }


def assert_public(data):
    if isinstance(data, dict):
        assert not data.keys() & {
            "contact",
            "contact_type",
            "contact_value",
            "token_hash",
            "session_id",
            "owner_session_id",
            "token",
        }
        for value in data.values():
            assert_public(value)
    elif isinstance(data, list):
        for item in data:
            assert_public(item)


def together(*actions):
    barrier = Barrier(len(actions))

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))
