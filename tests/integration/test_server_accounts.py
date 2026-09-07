import json
from collections import deque

import pytest


class FakeWebSocket:
    """The minimal async transport surface used by ``Server.Server.handler``."""

    def __init__(self, messages, on_send=None):
        self._messages = iter(messages)
        self._on_send = on_send
        self.sent = []
        self.close_called = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._messages)
        except StopIteration as error:
            raise StopAsyncIteration from error

    async def send(self, message):
        self.sent.append(json.loads(message))
        if self._on_send is not None:
            self._on_send(self.sent[-1])

    async def close(self):
        self.close_called = True


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.security
async def test_signup_returns_token_without_registering_an_active_connection(
    isolated_server_module,
):
    server = isolated_server_module
    socket = FakeWebSocket(
        [json.dumps({"action": "signup", "payload": {"username": "alice", "password": "pw"}})]
    )

    await server.handler(socket)

    response = socket.sent
    assert len(response) == 1
    assert response[0]["action"] == "signup_response"
    token = response[0]["token"]
    assert server.state.auth.validate_user_token("alice", token) is True
    assert server.state.CLIENTS == {}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_signup_returns_the_current_error_for_duplicate_or_invalid_credentials(
    isolated_server_module,
):
    server = isolated_server_module
    socket = FakeWebSocket(
        [
            json.dumps({"action": "signup", "payload": {"username": "alice", "password": "pw"}}),
            json.dumps({"action": "signup", "payload": {"username": "alice", "password": "different"}}),
            json.dumps({"action": "signup", "payload": {"username": "", "password": "pw"}}),
        ]
    )

    await server.handler(socket)

    assert socket.sent[0]["action"] == "signup_response"
    assert socket.sent[1:] == [
        {"error": "Username already taken"},
        {"error": "Username already taken"},
    ]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_login_registers_the_socket_before_responding_and_cleans_up_on_exit(
    isolated_server_module,
):
    server = isolated_server_module
    assert server.state.auth.signup("alice", "pw") is True
    registration_during_response = {}

    def capture_registration(response):
        if response.get("action") == "login_response":
            registration_during_response.update(server.state.CLIENTS)

    socket = FakeWebSocket(
        [json.dumps({"action": "login", "payload": {"username": "alice", "password": "pw"}})],
        on_send=capture_registration,
    )

    await server.handler(socket)

    response = socket.sent[0]
    assert response["action"] == "login_response"
    assert server.state.auth.validate_user_token("alice", response["token"]) is True
    assert registration_during_response["alice"][0] is socket
    assert registration_during_response["alice"][1:] == ([], deque())
    assert server.state.CLIENTS == {}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_login_failure_returns_the_current_error_without_registering_socket(
    isolated_server_module,
):
    server = isolated_server_module
    assert server.state.auth.signup("alice", "pw") is True
    socket = FakeWebSocket(
        [json.dumps({"action": "login", "payload": {"username": "alice", "password": "wrong"}})]
    )

    await server.handler(socket)

    assert socket.sent == [{"error": "Login failed"}]
    assert server.state.CLIENTS == {}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.security
@pytest.mark.xfail(
    strict=True,
    reason="BUG-SERVER-001: handler registers the untrimmed login username as the connection key",
)
async def test_login_registers_the_normalized_username(isolated_server_module):
    server = isolated_server_module
    assert server.state.auth.signup("alice", "pw") is True
    registered_users = set()

    def capture_registration(response):
        if response.get("action") == "login_response":
            registered_users.update(server.state.CLIENTS)

    socket = FakeWebSocket(
        [json.dumps({"action": "login", "payload": {"username": "  alice  ", "password": "pw"}})],
        on_send=capture_registration,
    )

    await server.handler(socket)

    assert registered_users == {"alice"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_heartbeat_returns_its_protocol_response_without_authentication(
    isolated_server_module,
):
    server = isolated_server_module
    socket = FakeWebSocket([json.dumps({"action": "heartbeat", "token": "invalid"})])

    await server.handler(socket)

    assert socket.sent == [{"action": "heartbeat"}]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.security
async def test_logout_revokes_a_valid_token_closes_socket_and_cleans_connection(
    isolated_server_module,
):
    server = isolated_server_module
    assert server.state.auth.signup("alice", "pw") is True
    token = server.state.auth.login("alice", "pw")
    socket = FakeWebSocket([json.dumps({"action": "logout", "token": token})])
    server.state.CLIENTS["alice"] = (socket, [], deque())

    await server.handler(socket)

    assert socket.sent == [{"action": "logout_response", "status": "success"}]
    assert socket.close_called is True
    assert server.state.auth.validate_user_token("alice", token) is False
    assert server.state.CLIENTS == {}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_logout_with_invalid_token_still_acknowledges_closes_and_cleans_connection(
    isolated_server_module,
):
    server = isolated_server_module
    socket = FakeWebSocket([json.dumps({"action": "logout", "token": "already-revoked"})])
    server.state.CLIENTS["alice"] = (socket, [], deque())

    await server.handler(socket)

    assert socket.sent == [{"action": "logout_response", "status": "success"}]
    assert socket.close_called is True
    assert server.state.CLIENTS == {}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("frame", [{"action": "unknown"}, {}])
async def test_unknown_or_missing_action_returns_an_error(isolated_server_module, frame):
    server = isolated_server_module
    socket = FakeWebSocket([json.dumps(frame)])

    await server.handler(socket)

    action = frame.get("action")
    assert socket.sent == [{"error": f"Unknown action: {action}"}]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_malformed_json_returns_error_and_handler_continues_to_next_request(
    isolated_server_module,
):
    server = isolated_server_module
    socket = FakeWebSocket(["{", json.dumps({"action": "heartbeat"})])

    await server.handler(socket)

    assert socket.sent == [{"error": "Invalid JSON format"}, {"action": "heartbeat"}]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_missing_username_in_account_requests_uses_the_current_failure_responses(
    isolated_server_module,
):
    server = isolated_server_module
    socket = FakeWebSocket(
        [json.dumps({"action": "signup", "payload": {}}), json.dumps({"action": "login", "payload": {}})]
    )

    await server.handler(socket)

    assert socket.sent == [{"error": "Username already taken"}, {"error": "Login failed"}]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.security
@pytest.mark.xfail(
    strict=True,
    reason="BUG-SERVER-002: signup silently substitutes a default password when one is omitted",
)
async def test_signup_rejects_a_request_without_password(isolated_server_module):
    server = isolated_server_module
    socket = FakeWebSocket([json.dumps({"action": "signup", "payload": {"username": "alice"}})])

    await server.handler(socket)

    assert socket.sent == [{"error": "Username already taken"}]
