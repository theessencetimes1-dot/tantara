"""PostgreSQL connections pin to IPv4, which is all Cloud Run egress offers."""

from __future__ import annotations

import socket

from app import db


def setup_function() -> None:
    db._address_cache.clear()


def test_postgres_hosts_are_resolved_to_ipv4(monkeypatch):
    seen: list[int | None] = []

    def fake_getaddrinfo(host, port, family=None, type=None):  # noqa: ANN001, A002
        seen.append(family)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.9", port))]

    monkeypatch.setattr(db.socket, "getaddrinfo", fake_getaddrinfo)
    assert db.postgres_connect_args("postgresql://user:pw@db.example.com:5432/postgres") == {
        "hostaddr": "203.0.113.9"
    }
    assert seen == [socket.AF_INET]


def test_the_resolved_address_is_cached(monkeypatch):
    calls: list[str] = []

    def fake_getaddrinfo(host, port, family=None, type=None):  # noqa: ANN001, A002
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.10", port))]

    monkeypatch.setattr(db.socket, "getaddrinfo", fake_getaddrinfo)
    url = "postgresql+psycopg://user:pw@db.example.com/postgres"
    assert db.postgres_connect_args(url) == {"hostaddr": "203.0.113.10"}
    assert db.postgres_connect_args(url) == {"hostaddr": "203.0.113.10"}
    assert calls == ["db.example.com"]


def test_sqlite_needs_no_connect_args():
    assert db.postgres_connect_args("sqlite:////tmp/tantara.db") == {}


def test_a_host_without_an_a_record_is_left_to_libpq(monkeypatch):
    def fail(host, port, family=None, type=None):  # noqa: ANN001, A002
        raise socket.gaierror("no IPv4")

    monkeypatch.setattr(db.socket, "getaddrinfo", fail)
    assert db.postgres_connect_args("postgresql://user:pw@db.example.com/postgres") == {}
    # The failure is remembered, so a cold start does not retry the lookup per connect.
    assert db._address_cache["db.example.com"] == ""
