"""In-process coverage for server message routing and room delivery."""

import json
from collections import deque

import pytest


class FakeRecipientSocket:
    """Minimal socket that records JSON frames and can fail delivery."""

    def __init__(self, *, fail_send=False):
        self.fail_send = fail_send
        self.sent = []
        self.send_attempts = 0

    async def send(self, message):
        self.send_attempts += 1
        if self.fail_send:
            raise RuntimeError("recipient socket is unavailable")
        self.sent.append(json.loads(message))


class FakeHandlerSocket(FakeRecipientSocket):
    """The handler-facing variant also supplies a finite async message stream."""

    def __init__(self, messages, *, on_send=None):
        super().__init__()
        self._messages = iter(messages)
        self._on_send = on_send

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._messages)
        except StopIteration as error:
            raise StopAsyncIteration from error

    async def send(self, message):
        await super().send(message)
        if self._on_send is not None:
            self._on_send(self.sent[-1])


def authenticated_user(server, username):
    assert server.state.auth.signup(username, "pw") is True
    return server.state.auth.login(username, "pw")


def message_frame(sender, address, message, token):
    return {
        "action": "send",
        "token": token,
        "payload": {"sender": sender, "address": address, "message": message},
    }


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("message", ["hello, 世界 👋", ""])
async def test_receive_delivers_direct_message_and_acknowledges_sender(isolated_server_module, message):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket = FakeRecipientSocket()
    recipient_socket = FakeRecipientSocket()
    server.state.CLIENTS["alice"] = (sender_socket, [], deque())
    server.state.CLIENTS["bob"] = (recipient_socket, [], deque())

    await server.messaging.receive(sender_socket, message_frame("alice", "bob", message, token))

    assert recipient_socket.sent == [{"action": "receive", "payload": {"sender": "alice", "address": "bob", "message": message}}]
    assert sender_socket.sent == [{"action": "ack", "payload": {"status": "success"}}]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_receive_reports_an_absent_direct_recipient(isolated_server_module):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket = FakeRecipientSocket()
    server.state.CLIENTS["alice"] = (sender_socket, [], deque())

    await server.messaging.receive(sender_socket, message_frame("alice", "nobody", "hello", token))

    assert sender_socket.sent == [{"error": "Address nobody not found"}]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_receive_reports_a_recipient_socket_delivery_failure(isolated_server_module):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket = FakeRecipientSocket()
    recipient_socket = FakeRecipientSocket(fail_send=True)
    server.state.CLIENTS.update({"alice": (sender_socket, [], deque()), "bob": (recipient_socket, [], deque())})

    await server.messaging.receive(sender_socket, message_frame("alice", "bob", "hello", token))

    assert recipient_socket.send_attempts == 1
    assert sender_socket.sent == [{"error": "Failed to send message to bob"}]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_receive_supports_direct_messages_to_the_sender(isolated_server_module):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket = FakeRecipientSocket()
    server.state.CLIENTS["alice"] = (sender_socket, [], deque())

    await server.messaging.receive(sender_socket, message_frame("alice", "alice", "note", token))

    assert sender_socket.sent == [
        {"action": "receive", "payload": {"sender": "alice", "address": "alice", "message": "note"}},
        {"action": "ack", "payload": {"status": "success"}},
    ]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_join_room_creates_membership_once_in_both_state_registries(isolated_server_module):
    server = isolated_server_module
    socket = FakeHandlerSocket([])
    server.state.CLIENTS["alice"] = (socket, [], deque())

    await server.manage_room(socket, "lobby", "alice")
    await server.manage_room(socket, "lobby", "alice")

    assert server.state.ROOMS == {"lobby": ["alice"]}
    assert server.state.CLIENTS["alice"][1] == ["lobby"]
    assert socket.sent == [{"action": "room_response", "payload": {"status": "success"}}] * 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_join_room_handler_path_exposes_membership_before_disconnect_cleanup(isolated_server_module):
    server = isolated_server_module
    snapshots = []

    def capture_membership(response):
        if response.get("action") == "room_response":
            snapshots.append((list(server.state.ROOMS["lobby"]), list(server.state.CLIENTS["alice"][1])))

    socket = FakeHandlerSocket(
        [json.dumps({"action": "join_room", "room_id": "lobby", "uid": "alice"})], on_send=capture_membership
    )
    server.state.CLIENTS["alice"] = (socket, [], deque())

    await server.handler(socket)

    assert snapshots == [(["alice"], ["lobby"])]
    assert server.state.CLIENTS == {}
    assert server.state.ROOMS == {"lobby": []}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_room_message_fans_out_to_other_members_and_acknowledges_sender(isolated_server_module):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket, bob_socket, carol_socket = FakeRecipientSocket(), FakeRecipientSocket(), FakeRecipientSocket()
    server.state.CLIENTS.update({
        "alice": (sender_socket, ["lobby"], deque()), "bob": (bob_socket, ["lobby"], deque()),
        "carol": (carol_socket, ["lobby"], deque()),
    })
    server.state.ROOMS["lobby"] = ["alice", "bob", "carol"]

    await server.messaging.receive(sender_socket, message_frame("alice", "lobby", "hello", token))

    expected = {"sender": "alice", "address": "lobby", "message": "hello"}
    assert bob_socket.sent == [{"action": "receive", "payload": expected}]
    assert carol_socket.sent == [{"action": "receive", "payload": expected}]
    assert sender_socket.sent == [{"action": "ack", "payload": {"status": "success"}}]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("members", [[], ["alice"]])
async def test_room_message_to_empty_or_sender_only_room_reports_failure(isolated_server_module, members):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket = FakeRecipientSocket()
    server.state.CLIENTS["alice"] = (sender_socket, ["lobby"], deque())
    server.state.ROOMS["lobby"] = members

    await server.messaging.receive(sender_socket, message_frame("alice", "lobby", "hello", token))

    assert sender_socket.sent == [{"error": "Failed to send message to lobby"}]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_room_delivery_attempts_other_members_despite_a_partial_failure(isolated_server_module):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket, successful_socket = FakeRecipientSocket(), FakeRecipientSocket()
    failing_socket, other_successful_socket = FakeRecipientSocket(fail_send=True), FakeRecipientSocket()
    server.state.CLIENTS.update({
        "alice": (sender_socket, ["lobby"], deque()), "user_a": (successful_socket, ["lobby"], deque()),
        "user_b": (failing_socket, ["lobby"], deque()), "user_c": (other_successful_socket, ["lobby"], deque()),
    })
    server.state.ROOMS["lobby"] = ["alice", "user_a", "user_b", "user_c"]

    await server.messaging.receive(sender_socket, message_frame("alice", "lobby", "hello", token))

    assert successful_socket.send_attempts == failing_socket.send_attempts == other_successful_socket.send_attempts == 1
    assert successful_socket.sent[0]["payload"]["message"] == "hello"
    assert other_successful_socket.sent[0]["payload"]["message"] == "hello"
    assert sender_socket.sent == [{"error": "Failed to send message to lobby"}]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_address_collision_routes_to_room_before_same_named_user(isolated_server_module):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    sender_socket, same_named_user_socket, room_member_socket = FakeRecipientSocket(), FakeRecipientSocket(), FakeRecipientSocket()
    server.state.CLIENTS.update({
        "alice": (sender_socket, [], deque()), "target": (same_named_user_socket, [], deque()),
        "room_member": (room_member_socket, [], deque()),
    })
    server.state.ROOMS["target"] = ["room_member"]

    await server.messaging.receive(sender_socket, message_frame("alice", "target", "hello", token))

    assert same_named_user_socket.sent == []
    assert room_member_socket.sent == [{"action": "receive", "payload": {"sender": "alice", "address": "target", "message": "hello"}}]
    assert sender_socket.sent == [{"action": "ack", "payload": {"status": "success"}}]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.security
@pytest.mark.xfail(strict=True, reason="BUG-SERVER-003: receive permits a sender claim over another user's registered socket")
async def test_receive_rejects_sender_claim_from_a_different_registered_socket(isolated_server_module):
    server = isolated_server_module
    alice_token = authenticated_user(server, "alice")
    bob_socket, recipient_socket = FakeRecipientSocket(), FakeRecipientSocket()
    server.state.CLIENTS.update({"bob": (bob_socket, [], deque()), "recipient": (recipient_socket, [], deque())})

    await server.messaging.receive(bob_socket, message_frame("alice", "recipient", "forged", alice_token))

    assert recipient_socket.sent == []
    assert bob_socket.sent == [{"error": "Sender/socket identity mismatch"}]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="BUG-SERVER-004: manage_room dispatch passes four arguments to a three-argument handler")
async def test_manage_room_action_joins_and_acknowledges_through_handler_dispatch(isolated_server_module):
    server = isolated_server_module
    token = authenticated_user(server, "alice")
    socket = FakeHandlerSocket([json.dumps({
        "action": "manage_room", "token": token, "payload": {"room_id": "lobby", "username": "alice"},
    })])
    server.state.CLIENTS["alice"] = (socket, [], deque())

    await server.handler(socket)

    assert socket.sent == [{"action": "room_response", "payload": {"status": "success"}}]
