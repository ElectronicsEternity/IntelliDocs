from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.services import retention


NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)


def capture(root, name, *, days=0, user="user-a", document="doc-a"):
    suffix = ".json.tmp" if name.endswith(".tmp") else ".json"
    path = root / "2026-10-06" / f"20261006-000000_{uuid5(NAMESPACE_URL, name)}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "started_at": (NOW - timedelta(days=days)).isoformat(),
        "user_id": user, "chunks": [{"document_id": document}],
    }), encoding="utf-8")
    return path


def test_debug_retention_uses_creation_and_configurable_cutoff(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RAG_DEBUG_CAPTURE_DIRECTORY", tmp_path)
    monkeypatch.setattr(settings, "DEBUG_RETENTION_DAYS", 14)
    old = capture(tmp_path, "old.json", days=15)
    boundary = capture(tmp_path, "boundary.json", days=14)
    fresh = capture(tmp_path, "fresh.json", days=13)
    assert retention.purge_debug_files(now=NOW) == 1
    assert not old.exists() and boundary.exists() and fresh.exists()
    monkeypatch.setattr(settings, "DEBUG_RETENTION_DAYS", 7)
    assert retention.purge_debug_files(now=NOW) == 2


def test_abandoned_temporary_file_and_unrelated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RAG_DEBUG_CAPTURE_DIRECTORY", tmp_path)
    old = capture(tmp_path, "old.json.tmp", days=15)
    invalid = capture(tmp_path, "incomplete.json.tmp")
    invalid.write_text("{", encoding="utf-8")
    timestamp = (NOW - timedelta(days=15)).timestamp()
    os.utime(invalid, (timestamp, timestamp))
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")
    assert retention.purge_debug_files(now=NOW) == 2
    assert not old.exists() and not invalid.exists() and unrelated.exists()


def test_document_support_is_owner_scoped_and_removes_all_caches(tmp_path, monkeypatch):
    profiles, debug = tmp_path / "profiles", tmp_path / "debug"
    monkeypatch.setattr(settings, "DOCUMENT_PROFILES_DIRECTORY", profiles)
    monkeypatch.setattr(settings, "RAG_DEBUG_CAPTURE_DIRECTORY", debug)
    target = profiles / "user-a" / "doc-a"
    target.mkdir(parents=True)
    for name in ("accepted_profile.json", "table_profile.json", "chunk_embeddings_0001.json", "attempt.json"):
        (target / name).write_text("{}", encoding="utf-8")
    sibling = profiles / "user-a" / "doc-b"
    sibling.mkdir()
    other_owner = profiles / "user-b" / "doc-a"
    other_owner.mkdir(parents=True)
    matching = capture(debug, "matching.json")
    other_doc = capture(debug, "other-document.json", document="doc-b")
    other_user = capture(debug, "other-user.json", user="user-b")
    retention.remove_document_support("user-a", "doc-a")
    assert not target.exists() and not matching.exists()
    assert sibling.exists() and other_owner.exists() and other_doc.exists() and other_user.exists()
    retention.remove_document_support("user-a", "doc-a")  # Safe retry.


def test_linked_cache_is_rejected(tmp_path, monkeypatch):
    profiles = tmp_path / "profiles"
    target = profiles / "user-a" / "doc-a"
    target.mkdir(parents=True)
    monkeypatch.setattr(settings, "DOCUMENT_PROFILES_DIRECTORY", profiles)
    monkeypatch.setattr(retention, "_linked", lambda path: path == target)
    with pytest.raises(ValueError, match="linked"):
        retention.remove_document_support("user-a", "doc-a")
    assert target.exists()


def test_cleanup_sql_targets_only_chat_tables(monkeypatch):
    queries = []

    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params=None): queries.append((sql, params))

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()

    monkeypatch.setattr(retention, "get_connection", Connection)
    monkeypatch.setattr(settings, "CHAT_RETENTION_DAYS", 3)
    result = retention.purge_chat_records(now=NOW)
    deletes = [(sql, params) for sql, params in queries if "DELETE" in sql]
    assert result == {"messages": 1, "conversations": 1}
    assert len(deletes) == 2
    assert deletes[0][1] == (NOW - timedelta(days=3),)
    assert "NOT EXISTS" in deletes[1][0]
    assert not any(term in sql for sql, _ in queries for term in ("ai_usage", "usage_records", "billing_"))


def test_debug_cleanup_still_runs_after_database_failure(monkeypatch):
    def unavailable(): raise RuntimeError("private credentials must never be logged")
    called = []
    monkeypatch.setattr(retention, "purge_chat_records", unavailable)
    monkeypatch.setattr(retention, "purge_debug_files", lambda: called.append(True))
    retention.run_cleanup()
    assert called == [True]


def test_retention_configuration_rejects_invalid_periods():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CHAT_RETENTION_DAYS=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DEBUG_RETENTION_DAYS=-1)


@pytest.mark.anyio
async def test_worker_runs_on_startup_and_stops_cleanly(monkeypatch):
    import asyncio
    stop = asyncio.Event()
    called = []
    def cleanup():
        called.append(True)
        stop.set()
    monkeypatch.setattr(retention, "run_cleanup", cleanup)
    await retention.retention_worker(stop)
    assert called == [True]


@pytest.mark.skipif(os.environ.get("TEST_RETENTION_DB") != "1", reason="Opt-in isolated temporary-table DB test")
def test_postgres_retention_preserves_recent_messages_and_ledgers(monkeypatch):
    # Every test table is temporary; never run DELETE against real user tables.
    from app.database.connection import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE conversations (id integer PRIMARY KEY, created_at timestamptz, updated_at timestamptz)")
            cur.execute("CREATE TEMP TABLE messages (id integer PRIMARY KEY, conversation_id integer REFERENCES conversations(id) ON DELETE CASCADE, created_at timestamptz)")
            for table in ("ai_usage", "usage_records", "billing_events", "billing_periods", "billing_accounts"):
                cur.execute(f"CREATE TEMP TABLE {table} (id integer)")
                cur.execute(f"INSERT INTO {table} VALUES (1)")
            old, recent = NOW - timedelta(days=15), NOW - timedelta(days=1)
            cur.executemany("INSERT INTO conversations VALUES (%s, %s, %s)", [(1, old, old), (2, old, old), (3, recent, recent)])
            cur.executemany("INSERT INTO messages VALUES (%s, %s, %s)", [(1, 1, old), (2, 2, old), (3, 2, recent), (4, 3, recent)])

        @contextmanager
        def temporary_connection():
            yield conn

        monkeypatch.setattr(retention, "get_connection", temporary_connection)
        monkeypatch.setattr(settings, "CHAT_RETENTION_DAYS", 14)
        assert retention.purge_chat_records(now=NOW) == {"messages": 2, "conversations": 1}
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM messages ORDER BY id")
            assert cur.fetchall() == [(3,), (4,)]
            for table in ("ai_usage", "usage_records", "billing_events", "billing_periods", "billing_accounts"):
                cur.execute(f"SELECT count(*) FROM {table}")
                assert cur.fetchone()[0] == 1
        conn.rollback()
