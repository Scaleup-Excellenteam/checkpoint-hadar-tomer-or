"""Isolated request and control-response tests for :mod:`client`."""

import json
import queue

import pytest

import client


class FakeConnection:
    """Small synchronous transport that records exactly what the client sends."""

    def __init__(self, send_error=None):
        self.sent = []
        self.send_error = send_error
        self.closed = False

    def send(self, raw):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(raw)

    def close(self):
        self.closed = True


class InertThread:
    """Prevents constructor coverage from creating a real listener."""

    def __init__(self, *, target, daemon):
        self.target = target
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True


class EmptyControlQueue:
    """Deterministically simulates a control-response timeout."""

    def get(self, *, timeout):
        assert timeout == 5
        raise queue.Empty


class FakeHistory:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def client_factory(monkeypatch):
    """Construct clients without TLS, sockets, or listener threads."""
    class FakeSSLContext:
        check_hostname = True

    def connect(uri, ssl):
        return FakeConnection()

    monkeypatch.setattr(client.ssl, "create_default_context", lambda **kwargs: FakeSSLContext())
    monkeypatch.setattr(client, "connect", connect)
    monkeypatch.setattr(client.threading, "Thread", InertThread)

    def create(*args, **kwargs):
        instance = client.ChatClient(*args, **kwargs)
        assert isinstance(instance._listener_thread, InertThread)
        assert instance._listener_thread.started is True
        return instance

    return create


def sent_json(chat_client):
    return [json.loads(raw) for raw in chat_client.socket.sent]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "port", "expected_uri"),
    [("127.0.0.1", 9000, "wss://127.0.0.1:9000"), ("wss://chat.example.test/socket", 1234, "wss://chat.example.test/socket")],
)
def test_constructor_sets_uri_and_unauthenticated_initial_state(client_factory, host, port, expected_uri):
    chat_client = client_factory(host=host, port=port)

    assert chat_client.uri == expected_uri
    assert chat_client.username is None
    assert chat_client.token is None
    assert chat_client.current_target is None
    assert chat_client.history_db is None
    assert isinstance(chat_client._control_queue, queue.Queue)


@pytest.mark.unit
def test_signup_serializes_request_and_does_not_log_the_client_in(client_factory):
    chat_client = client_factory()
    chat_client._control_queue.put({"action": "signup_response", "token": "issued-token"})

    assert chat_client.signup("alice", "pw") is True
    assert sent_json(chat_client) == [{"action": "signup", "payload": {"username": "alice", "password": "pw"}}]
    assert (chat_client.username, chat_client.token, chat_client.current_target) == (None, None, None)


@pytest.mark.unit
def test_signup_error_and_timeout_return_false_without_authentication(client_factory):
    chat_client = client_factory()
    chat_client._control_queue.put({"error": "Username already taken"})

    assert chat_client.signup("alice", "pw") is False
    chat_client._control_queue = EmptyControlQueue()
    assert chat_client.signup("bob", "pw") is False
    assert chat_client.token is None


@pytest.mark.unit
def test_login_serializes_request_sets_auth_state_and_opens_history(client_factory, monkeypatch):
    chat_client = client_factory()
    opened = []
    monkeypatch.setattr(chat_client, "_open_history_db", lambda: opened.append(True))
    chat_client._control_queue.put({"action": "login_response", "token": "alice-token"})

    assert chat_client.login("alice", "pw") is True
    assert sent_json(chat_client) == [{"action": "login", "payload": {"username": "alice", "password": "pw"}}]
    assert (chat_client.username, chat_client.token) == ("alice", "alice-token")
    assert opened == [True]


@pytest.mark.unit
def test_login_error_and_timeout_preserve_existing_auth_state(client_factory):
    chat_client = client_factory()
    chat_client.username = "existing"
    chat_client.token = "existing-token"
    chat_client._control_queue.put({"error": "Login failed"})

    assert chat_client.login("alice", "wrong") is False
    chat_client._control_queue = EmptyControlQueue()
    assert chat_client.login("alice", "pw") is False
    assert (chat_client.username, chat_client.token) == ("existing", "existing-token")


@pytest.mark.unit
def test_logout_success_serializes_request_clears_state_and_closes_history(client_factory):
    chat_client = client_factory()
    history = FakeHistory()
    chat_client.username, chat_client.token, chat_client.current_target = "alice", "token", "room-1"
    chat_client.history_db = history
    chat_client._control_queue.put({"action": "logout_response", "status": "success"})

    assert chat_client.logout() is True
    assert sent_json(chat_client) == [{"action": "logout", "token": "token"}]
    assert (chat_client.username, chat_client.token, chat_client.current_target) == (None, None, None)
    assert history.closed is True
    assert chat_client.history_db is None


@pytest.mark.unit
def test_logout_error_timeout_or_missing_token_preserves_state(client_factory):
    chat_client = client_factory()
    chat_client.username, chat_client.token, chat_client.current_target = "alice", "token", "room-1"
    chat_client._control_queue.put({"error": "logout denied"})

    assert chat_client.logout() is False
    chat_client._control_queue = EmptyControlQueue()
    assert chat_client.logout() is False
    assert (chat_client.username, chat_client.token, chat_client.current_target) == ("alice", "token", "room-1")
    chat_client.token = None
    assert chat_client.logout() is False
    assert len(chat_client.socket.sent) == 2


@pytest.mark.unit
def test_heartbeat_serializes_request_and_returns_the_server_packet(client_factory):
    chat_client = client_factory()
    response = {"action": "heartbeat"}
    chat_client._control_queue.put(response)

    assert chat_client.heartbeat() == response
    assert sent_json(chat_client) == [{"action": "heartbeat"}]
    chat_client._control_queue = EmptyControlQueue()
    assert chat_client.heartbeat() is None


@pytest.mark.unit
def test_join_room_updates_target_only_for_successful_room_response(client_factory):
    chat_client = client_factory()
    chat_client.username, chat_client.current_target = "alice", "prior"
    chat_client._control_queue.put({"action": "room_response", "payload": {"status": "success"}})

    assert chat_client.join_room("team") is True
    assert chat_client.current_target == "team"
    assert sent_json(chat_client) == [{"action": "join_room", "room_id": "team", "uid": "alice"}]

    chat_client._control_queue.put({"action": "room_response", "payload": {"status": "failure"}})
    assert chat_client.join_room("other") is False
    assert chat_client.current_target == "team"


@pytest.mark.unit
def test_start_chat_is_local_target_selection(client_factory):
    chat_client = client_factory()

    assert chat_client.start_chat("bob") == {"status": "ok", "chatting_with": "bob"}
    assert chat_client.current_target == "bob"
    assert chat_client.socket.sent == []


@pytest.mark.unit
def test_send_message_serializes_explicit_and_current_targets_and_returns_send_attempt_success(client_factory, monkeypatch):
    chat_client = client_factory()
    chat_client.username, chat_client.token, chat_client.current_target = "alice", "token", "room-1"
    saved = []
    monkeypatch.setattr(chat_client, "_save_history", lambda *args: saved.append(args))

    assert chat_client.send_message("bob", "hello") is True
    assert chat_client.send_message(None, "room hello") is True
    assert sent_json(chat_client) == [
        {"action": "send", "token": "token", "payload": {"sender": "alice", "address": "bob", "message": "hello"}},
        {"action": "send", "token": "token", "payload": {"sender": "alice", "address": "room-1", "message": "room hello"}},
    ]
    assert saved == [("bob", "alice", "sent", "hello"), ("room-1", "alice", "sent", "room hello")]


@pytest.mark.unit
def test_send_message_requires_token_and_target_and_propagates_send_errors(client_factory, monkeypatch):
    chat_client = client_factory()
    assert chat_client.send_message("bob", "hello") is False
    chat_client.token = "token"
    assert chat_client.send_message(None, "hello") is False

    saved = []
    monkeypatch.setattr(chat_client, "_save_history", lambda *args: saved.append(args))
    chat_client.username = "alice"
    chat_client.socket.send_error = OSError("connection lost")
    with pytest.raises(OSError, match="connection lost"):
        chat_client.send_message("bob", "hello")
    assert saved == []


@pytest.mark.unit
def test_close_closes_socket_and_history_connection(client_factory):
    chat_client = client_factory()
    history = FakeHistory()
    chat_client.history_db = history

    assert chat_client.close() is None
    assert chat_client.socket.closed is True
    assert history.closed is True
    assert chat_client.history_db is None


@pytest.mark.unit
@pytest.mark.xfail(strict=True, reason="BUG-CLIENT-001: stale acknowledgements are consumed as control responses")
def test_heartbeat_does_not_consume_a_stale_send_acknowledgement(client_factory):
    chat_client = client_factory()
    stale_ack = {"action": "ack", "payload": {"status": "success"}}
    expected = {"action": "heartbeat"}
    chat_client._control_queue.put(stale_ack)
    chat_client._control_queue.put(expected)

    assert chat_client.heartbeat() == expected


@pytest.mark.unit
@pytest.mark.xfail(strict=True, reason="BUG-CLIENT-002: login accepts unrelated token-bearing control responses")
def test_login_rejects_an_unrelated_token_bearing_response(client_factory, monkeypatch):
    chat_client = client_factory()
    monkeypatch.setattr(chat_client, "_open_history_db", lambda: None)
    chat_client._control_queue.put({"action": "signup_response", "token": "unrelated-token"})

    assert chat_client.login("alice", "pw") is False
    assert (chat_client.username, chat_client.token) == (None, None)
