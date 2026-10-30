"""Run the MeetPoint demo against an already running server, using only the stdlib."""

import argparse
import json
import sys
from datetime import date, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
from xml.etree import ElementTree


class DemoError(Exception):
    pass


class Client:
    def __init__(self, base_url):
        self.base_url = base_url
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, method, path, payload=None, *, expected=200, raw=False):
        body = None if payload is None else json.dumps(payload).encode()
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            try:
                response = self.opener.open(request, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                if response.status != expected:
                    raise DemoError(f"{method} {path}: expected {expected}, got {response.status}")
                if expected >= 400:
                    return None
                content = response.read()
                return content if raw else json.loads(content)
        except (URLError, TimeoutError):
            raise DemoError(f"{method} {path}: server unavailable") from None


def is_public(data):
    private = set(
        "contact contact_type contact_value session_id owner_session_id token token_hash".split()
    )
    if isinstance(data, dict):
        return private.isdisjoint(data) and all(is_public(value) for value in data.values())
    return not isinstance(data, list) or all(is_public(value) for value in data)


def run_demo(base_url, report):
    def check(condition, name):
        if not condition:
            raise DemoError(name)
        report["checks_passed"].append(name)
        print(f"PASS {name}")

    organizer, alice, bob = [Client(base_url) for _ in range(3)]
    check(organizer.request("GET", "/health") == {"status": "ok"}, "health")
    for client in (organizer, alice, bob):
        client.request("POST", "/api/session")
    check(True, "three independent sessions")
    event_data = {
        "name": "MeetPoint CI demo",
        "date": str(date.today() + timedelta(days=1)),
        "description": "Synthetic data for the automated demo.",
        "tags": ["python", "postgres", "backend", "design"],
    }
    event = organizer.request("POST", "/api/events", event_data, expected=201)
    report["event_id"] = event["id"]
    path = f"/api/events/{event['id']}"
    check(is_public(event), "public event")
    check(urlsplit(event["join_url"]).path == path, "event link points to API")
    check(organizer.request("GET", path) == event, "event link returns JSON")
    qr = organizer.request("GET", f"{path}/qr.svg", raw=True)
    check(ElementTree.fromstring(qr).tag.endswith("svg"), "event QR")
    profiles = []
    for client, name in ((alice, "Alice"), (bob, "Bob")):
        profile = {
            "name": name,
            "role": "Demo participant",
            "tag_ids": [tag["id"] for tag in event["tags"][:3]],
            "contact": {"type": "email", "value": f"{name.lower()}@example.com"},
        }
        profiles.append(client.request("PUT", f"{path}/me", profile))
    check(profiles[0]["id"] != profiles[1]["id"], "two distinct profiles")
    for client, peer in ((alice, profiles[1]), (bob, profiles[0])):
        for suffix in ("participants", "recommendations"):
            data = client.request("GET", f"{path}/{suffix}")
            check(
                is_public(data) and [item["id"] for item in data["items"]] == [peer["id"]],
                f"private contact hidden in {suffix}",
            )
    payload = {"recipient_id": profiles[1]["id"]}
    invitation = alice.request("POST", f"{path}/requests", payload, expected=201)
    check(is_public(invitation), "invitation hides contacts")
    incoming = bob.request("GET", f"{path}/requests")
    check(is_public(incoming) and len(incoming["items"]) == 1, "recipient sees invitation")
    for client in (alice, bob):
        check(client.request("GET", f"{path}/contacts")["items"] == [], "no contact before consent")
    accepted = bob.request("PATCH", f"{path}/requests/{invitation['id']}", {"status": "accepted"})
    check(accepted["status"] == "accepted" and is_public(accepted), "recipient accepts invitation")
    for client, peer in ((alice, profiles[1]), (bob, profiles[0])):
        check(client.request("GET", f"{path}/contacts")["items"] == [peer], "mutual contact access")
    alice.request("POST", f"{path}/requests", payload, expected=409)
    check(True, "duplicate invitation rejected")
    statistics = organizer.request("GET", f"{path}/stats")
    expected_stats = {
        "participants_count": 2,
        "requests_sent": 1,
        "requests_accepted": 1,
        "connections_count": 1,
    }
    check(statistics == expected_stats, "organizer statistics")
    report["statistics"] = statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--report", type=Path, default=Path("reports/demo.json"))
    args = parser.parse_args()
    report = {"checks_passed": [], "event_id": None, "statistics": {}}
    exit_code = 0
    try:
        base_url = args.base_url.rstrip("/")
        url = urlsplit(base_url)
        invalid_origin = url.username or url.password or url.path or url.query or url.fragment
        if url.scheme not in ("http", "https") or not url.hostname or invalid_origin:
            raise DemoError("base URL must be an HTTP(S) origin without credentials")
        run_demo(base_url, report)
    except DemoError as error:
        report["error"] = str(error)
        exit_code = 1
    except (ValueError, TypeError, KeyError, ElementTree.ParseError):
        report["error"] = "Unexpected server response format"
        exit_code = 1
    if exit_code:
        print(f"FAIL {report['error']}", file=sys.stderr)
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError:
        print("FAIL could not write demo report", file=sys.stderr)
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
