"""Incoming packet classification tests for :mod:`client`."""

import json

import pytest

from tests.unit.test_client_controls import FakeConnection, client_factory


def run_scripted_listener(chat_client, packets):
    """Feed decoded packets directly to one synchronous listener invocation."""
    iterator = iter([*packets, None])
    chat_client._raw_recv = lambda: next(iterator)
    chat_client._listen_loop()


@pytest.mark.unit
def test_direct_receive_is_saved_before_callback_with_sender_as_chat_id(client_factory, monkeypatch):
    chat_client = client_factory()
    chat_client.username = "alice"
    saved = []
    callback_observations = []
    monkeypatch.setattr(chat_client, "_save_history", lambda *row: saved.append(row))
    chat_client.set_message_handler(lambda *message: callback_observations.append((message, list(saved))))

    run_scripted_listener(chat_client, [{"action": "receive", "payload": {"sender": "bob", "address": "alice", "message": "hello"}}])

    assert saved == [("bob", "bob", "received", "hello")]
    assert callback_observations == [(("bob", "bob", "hello"), list(saved))]


@pytest.mark.unit
def test_room_receive_is_saved_and_reported_under_room_address(client_factory, monkeypatch):
    chat_client = client_factory()
    chat_client.username = "alice"
    saved = []
    seen = []
    monkeypatch.setattr(chat_client, "_save_history", lambda *row: saved.append(row))
    chat_client.set_message_handler(lambda *message: seen.append(message))

    run_scripted_listener(chat_client, [{"action": "receive", "payload": {"sender": "bob", "address": "room-7", "message": "team update"}}])

    assert saved == [("room-7", "bob", "received", "team update")]
    assert seen == [("room-7", "bob", "team update")]


@pytest.mark.unit
def test_receive_without_callback_still_saves_history(client_factory, monkeypatch):
    chat_client = client_factory()
    chat_client.username = "alice"
    saved = []
    monkeypatch.setattr(chat_client, "_save_history", lambda *row: saved.append(row))

    run_scripted_listener(chat_client, [{"action": "receive", "payload": {"sender": "bob", "address": "alice", "message": "hello"}}])

    assert saved == [("bob", "bob", "received", "hello")]


@pytest.mark.unit
@pytest.mark.parametrize("packet", [
    {"action": "ack"},
    {"action": "login_response", "token": "token"},
    {"action": "logout_response"},
    {"action": "room_response", "payload": {"status": "success"}},
    {"action": "heartbeat"},
    {"error": "control failure"},
])
def test_control_packets_are_queued_without_history_rows(client_factory, monkeypatch, packet):
    chat_client = client_factory()
    saved = []
    monkeypatch.setattr(chat_client, "_save_history", lambda *row: saved.append(row))

    run_scripted_listener(chat_client, [packet])

    assert saved == []
    assert chat_client._control_queue.get_nowait() == packet


@pytest.mark.unit
def test_raw_recv_parses_valid_json_and_ends_on_malformed_or_closed_input(client_factory):
    chat_client = client_factory()
    chat_client.socket = FakeConnection()
    frames = iter([json.dumps({"action": "receive"}), "{bad json", ""])
    chat_client.socket.recv = lambda: next(frames)

    assert chat_client._raw_recv() == {"action": "receive"}
    assert chat_client._raw_recv() is None
    assert chat_client._raw_recv() is None


@pytest.mark.unit
def test_raw_recv_returns_non_object_json_but_listener_cannot_classify_it(client_factory):
    chat_client = client_factory()
    chat_client.socket = FakeConnection()
    chat_client.socket.recv = lambda: "[]"
    assert chat_client._raw_recv() == []

    chat_client._raw_recv = lambda: []
    with pytest.raises(AttributeError):
        chat_client._listen_loop()


@pytest.mark.unit
@pytest.mark.xfail(strict=True, reason="BUG-CLIENT-003: message-handler exceptions terminate the listener")
def test_callback_exception_does_not_stop_later_incoming_messages(client_factory, monkeypatch):
    chat_client = client_factory()
    chat_client.username = "alice"
    saved = []
    monkeypatch.setattr(chat_client, "_save_history", lambda *row: saved.append(row))

    def failing_handler(*_message):
        raise RuntimeError("handler failed")

    chat_client.set_message_handler(failing_handler)
    packets = [
        {"action": "receive", "payload": {"sender": "bob", "address": "alice", "message": "first"}},
        {"action": "receive", "payload": {"sender": "carol", "address": "alice", "message": "second"}},
    ]
    run_scripted_listener(chat_client, packets)

    assert saved == [("bob", "bob", "received", "first"), ("carol", "carol", "received", "second")]
