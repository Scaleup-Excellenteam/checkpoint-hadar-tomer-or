"""SQLite history integration tests for :mod:`client`."""

from datetime import datetime, timezone
import sqlite3

import pytest

from tests.unit.test_client_controls import client_factory


@pytest.fixture
def history_client(client_factory, tmp_path):
    """An authenticated client backed by one real, temporary history database."""
    instance = client_factory(history_db=str(tmp_path / "alice-history.db"))
    instance.username = "alice"
    instance.token = "alice-token"
    instance._open_history_db()
    yield instance
    instance.close()


@pytest.mark.integration
def test_history_is_unavailable_until_opened_after_login(client_factory):
    chat_client = client_factory(history_db="not-created.db")

    assert chat_client.get_history() == []
    chat_client._save_history("bob", "alice", "sent", "not persisted")
    assert chat_client.history_db is None

    chat_client.close()


@pytest.mark.integration
def test_open_history_db_creates_schema_at_explicit_temporary_path_and_reopens(client_factory, tmp_path):
    history_path = tmp_path / "chosen-history.db"
    first = client_factory(history_db=str(history_path))
    first.username = "alice"
    first._open_history_db()
    first._save_history("bob", "alice", "sent", "persist me")
    first.close()

    assert history_path.exists()
    second = client_factory(history_db=str(history_path))
    second.username = "alice"
    second._open_history_db()
    rows = second.get_history("bob")
    assert len(rows) == 1
    assert rows[0][:4] == ("bob", "alice", "sent", "persist me")
    assert datetime.fromisoformat(rows[0][4]).tzinfo == timezone.utc
    second.close()


@pytest.mark.integration
def test_default_history_paths_are_per_user_and_can_be_redirected_to_temp_directory(client_factory, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    alice = client_factory()
    bob = client_factory()
    alice.username = "alice"
    bob.username = "bob"
    alice._open_history_db()
    bob._open_history_db()
    alice._save_history("shared", "alice", "sent", "alice only")
    bob._save_history("shared", "bob", "sent", "bob only")

    assert (tmp_path / "DB" / "chat_history_alice.db").exists()
    assert (tmp_path / "DB" / "chat_history_bob.db").exists()
    assert [row[3] for row in alice.get_history("shared")] == ["alice only"]
    assert [row[3] for row in bob.get_history("shared")] == ["bob only"]

    alice.close()
    bob.close()


@pytest.mark.integration
@pytest.mark.parametrize("message", ["hello 🌍", "", "'); DROP TABLE messages; --"])
def test_successful_outgoing_send_persists_exact_message_and_utc_timestamp(history_client, message):
    assert history_client.send_message("bob", message) is True

    row = history_client.get_history("bob")
    assert len(row) == 1
    chat_id, sender, direction, stored_message, timestamp = row[0]
    assert (chat_id, sender, direction, stored_message) == ("bob", "alice", "sent", message)
    assert datetime.fromisoformat(timestamp).tzinfo == timezone.utc


@pytest.mark.integration
def test_send_failure_or_missing_authentication_or_target_does_not_persist_outgoing_history(history_client):
    history_client.socket.send_error = OSError("connection lost")
    with pytest.raises(OSError, match="connection lost"):
        history_client.send_message("bob", "not stored")
    assert history_client.get_history() == []

    history_client.socket.send_error = None
    history_client.token = None
    assert history_client.send_message("bob", "not stored") is False
    history_client.token = "alice-token"
    assert history_client.send_message(None, "not stored") is False
    assert history_client.get_history() == []


@pytest.mark.integration
def test_get_history_filters_chats_and_returns_latest_rows_in_chronological_order(history_client):
    for chat_id, message in [("bob", "one"), ("room-1", "room"), ("bob", "two"), ("bob", "three")]:
        history_client._save_history(chat_id, "alice", "sent", message)

    assert [row[3] for row in history_client.get_history("bob")] == ["one", "two", "three"]
    assert [row[3] for row in history_client.get_history("room-1")] == ["room"]
    assert history_client.get_history("nobody") == []
    assert [row[3] for row in history_client.get_history("bob", limit=2)] == ["two", "three"]
    assert history_client.get_history("bob", limit=0) == []


@pytest.mark.integration
def test_logout_and_close_release_history_database_for_reopening(client_factory, tmp_path):
    history_path = tmp_path / "reopenable.db"
    logout_client = client_factory(history_db=str(history_path))
    logout_client.username, logout_client.token = "alice", "token"
    logout_client._open_history_db()
    logout_client._save_history("bob", "alice", "sent", "before logout")
    logout_client._control_queue.put({"action": "logout_response"})
    assert logout_client.logout() is True
    assert logout_client.history_db is None

    reopened = sqlite3.connect(history_path)
    assert reopened.execute("SELECT message FROM messages").fetchall() == [("before logout",)]
    reopened.close()

    close_client = client_factory(history_db=str(history_path))
    close_client.username = "alice"
    close_client._open_history_db()
    close_client.close()
    reopened_again = sqlite3.connect(history_path)
    assert reopened_again.execute("SELECT count(*) FROM messages").fetchone() == (1,)
    reopened_again.close()
