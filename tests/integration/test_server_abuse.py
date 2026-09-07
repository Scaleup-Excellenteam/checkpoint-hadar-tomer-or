"""Deterministic rate-limit and authentication-boundary coverage."""

from collections import deque

import pytest

from test_server_messaging import FakeRecipientSocket, authenticated_user, message_frame


class FakeClock:
    """A minimal explicit clock for ``Server.messaging.time.monotonic``."""

    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def register_self(server, username, socket):
    server.state.CLIENTS[username] = (socket, [], deque())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rate_limit_allows_configured_attempts_rejects_next_and_expires_after_window(
    isolated_server_module, monkeypatch
):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    socket = FakeRecipientSocket()
    register_self(server, "alice", socket)
    clock = FakeClock(100.0)
    monkeypatch.setattr(server.messaging.time, "monotonic", clock)

    for _ in range(server.state.MAX_MESSAGES):
        await server.messaging.receive(socket, message_frame("alice", "alice", "allowed", token))

    assert len(server.state.CLIENTS["alice"][2]) == server.state.MAX_MESSAGES
    assert [frame["action"] for frame in socket.sent].count("ack") == server.state.MAX_MESSAGES
    assert server.state.auth.get_reputation(token) == 0

    await server.messaging.receive(socket, message_frame("alice", "alice", "rejected", token))
    assert socket.sent[-1] == {"error": "Rate limit exceeded"}
    assert len(server.state.CLIENTS["alice"][2]) == server.state.MAX_MESSAGES
    assert server.state.auth.get_reputation(token) == server.state.SPAM_HIT

    clock.value = 130.0
    await server.messaging.receive(socket, message_frame("alice", "alice", "boundary", token))
    assert socket.sent[-1] == {"error": "Rate limit exceeded"}
    assert len(server.state.CLIENTS["alice"][2]) == server.state.MAX_MESSAGES

    clock.value = 130.001
    await server.messaging.receive(socket, message_frame("alice", "alice", "expired", token))
    assert socket.sent[-1] == {"action": "ack", "payload": {"status": "success"}}
    assert list(server.state.CLIENTS["alice"][2]) == [130.001]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rate_limits_and_reputation_are_independent_per_user(isolated_server_module, monkeypatch):
    server = isolated_server_module
    alice_token = authenticated_user(server, "alice")
    bob_token = authenticated_user(server, "bob")
    alice_socket, bob_socket = FakeRecipientSocket(), FakeRecipientSocket()
    register_self(server, "alice", alice_socket)
    register_self(server, "bob", bob_socket)
    monkeypatch.setattr(server.messaging.time, "monotonic", FakeClock(100.0))

    for _ in range(server.state.MAX_MESSAGES):
        await server.messaging.receive(alice_socket, message_frame("alice", "alice", "allowed", alice_token))
    for _ in range(2):
        await server.messaging.receive(alice_socket, message_frame("alice", "alice", "rejected", alice_token))
    await server.messaging.receive(bob_socket, message_frame("bob", "bob", "allowed", bob_token))

    assert len(server.state.CLIENTS["alice"][2]) == server.state.MAX_MESSAGES
    assert list(server.state.CLIENTS["bob"][2]) == [100.0]
    assert alice_socket.sent[-1] == {"error": "Rate limit exceeded"}
    assert bob_socket.sent[-1] == {"action": "ack", "payload": {"status": "success"}}
    assert server.state.auth.get_reputation(alice_token) == server.state.SPAM_HIT * 2
    assert server.state.auth.get_reputation(bob_token) == 0


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("address", ["missing-user", "missing-room"])
async def test_authenticated_missing_destinations_consume_rate_limit_budget(
    isolated_server_module, monkeypatch, address
):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    socket = FakeRecipientSocket()
    register_self(server, "alice", socket)
    clock = FakeClock(100.0)
    monkeypatch.setattr(server.messaging.time, "monotonic", clock)
    server.state.CLIENTS["alice"] = (socket, [], deque([100.0] * (server.state.MAX_MESSAGES - 1)))

    await server.messaging.receive(socket, message_frame("alice", address, "missing", token))

    assert socket.sent == [{"error": f"Address {address} not found"}]
    assert len(server.state.CLIENTS["alice"][2]) == server.state.MAX_MESSAGES
    await server.messaging.receive(socket, message_frame("alice", "alice", "next", token))
    assert socket.sent[-1] == {"error": "Rate limit exceeded"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_authenticated_delivery_failure_consumes_rate_limit_budget(isolated_server_module, monkeypatch):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket, failing_socket = FakeRecipientSocket(), FakeRecipientSocket(fail_send=True)
    clock = FakeClock(100.0)
    monkeypatch.setattr(server.messaging.time, "monotonic", clock)
    server.state.CLIENTS.update({
        "alice": (sender_socket, [], deque([100.0] * (server.state.MAX_MESSAGES - 1))),
        "bob": (failing_socket, [], deque()),
    })

    await server.messaging.receive(sender_socket, message_frame("alice", "bob", "fails", token))

    assert sender_socket.sent == [{"error": "Failed to send message to bob"}]
    assert len(server.state.CLIENTS["alice"][2]) == server.state.MAX_MESSAGES
    assert failing_socket.send_attempts == 1


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.security
@pytest.mark.parametrize("kind", ["missing", "random", "revoked", "other_user"])
async def test_invalid_authentication_neither_delivers_nor_consumes_budget(
    isolated_server_module, kind
):
    server = isolated_server_module
    alice_token = authenticated_user(server, "alice")
    if kind == "missing":
        token = None
    elif kind == "random":
        token = "not-a-session-token"
    elif kind == "revoked":
        token = alice_token
        assert server.state.auth.logout(token) is True
    else:
        token = authenticated_user(server, "bob")

    alice_socket, recipient_socket = FakeRecipientSocket(), FakeRecipientSocket()
    register_self(server, "alice", alice_socket)
    server.state.CLIENTS["recipient"] = (recipient_socket, [], deque())
    recipient_entry = server.state.CLIENTS["recipient"]

    await server.messaging.receive(alice_socket, message_frame("alice", "recipient", "blocked", token))

    assert alice_socket.sent == [{"error": "Auth failed"}]
    assert recipient_socket.sent == []
    assert server.state.CLIENTS["alice"][2] == deque()
    assert server.state.CLIENTS["recipient"] is recipient_entry


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.security
@pytest.mark.xfail(
    strict=True,
    reason="BUG-SERVER-005: receive replaces an existing connection mapping before authentication fails",
)
async def test_rejected_authentication_does_not_replace_a_victim_connection_mapping(isolated_server_module):
    server = isolated_server_module
    victim_socket, attacker_socket, recipient_socket = (
        FakeRecipientSocket(),
        FakeRecipientSocket(),
        FakeRecipientSocket(),
    )
    server.state.CLIENTS.update({
        "victim": (victim_socket, ["lobby"], deque([12.0])),
        "recipient": (recipient_socket, [], deque()),
    })
    original_victim_entry = server.state.CLIENTS["victim"]

    await server.messaging.receive(attacker_socket, message_frame("victim", "recipient", "forged", "invalid"))

    assert attacker_socket.sent == [{"error": "Auth failed"}]
    assert recipient_socket.sent == []
    assert server.state.CLIENTS["victim"] is original_victim_entry


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.security
@pytest.mark.xfail(
    strict=True,
    reason="BUG-SERVER-006: receive accepts the destination address as an alternative authentication token",
)
async def test_receive_requires_the_designated_token_field_not_a_token_in_address(isolated_server_module):
    server = isolated_server_module
    alice_token = authenticated_user(server, "alice")
    sender_socket, recipient_socket = FakeRecipientSocket(), FakeRecipientSocket()
    server.state.CLIENTS[alice_token] = (recipient_socket, [], deque())

    await server.messaging.receive(sender_socket, message_frame("alice", alice_token, "forged", "invalid"))

    assert sender_socket.sent == [{"error": "Auth failed"}]
    assert recipient_socket.sent == []
    assert server.state.CLIENTS["alice"][2] == deque()
