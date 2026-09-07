# Known issues

## BUG-AUTH-001 — Expired JWTs remain valid while present in memory

- **Reproduction:** Create a correctly signed token whose `exp` claim is in the past, add it to `AuthManager.sessions` for its user, then call `validate_user_token`.
- **Status:** Resolved. The regression is now a normal passing test.
- **Previous behavior:** `validate_user_token` returned `True` because it only checked the in-memory token-to-user mapping and never decoded or validated JWT claims.
- **Fix:** Require an active session for the requested user plus a JWT verified with the existing secret and explicit project algorithm. Require `exp` and `username`, enforce expiration and signed username matching, and return `False` on JWT validation errors. Validation leaves sessions unchanged.
- **Desired behavior:** An expired token must be rejected even if it remains in the session map.
- **Affected test:** `tests/integration/test_auth.py::test_validate_user_token_rejects_an_expired_signed_token`

## BUG-SERVER-001 — Whitespace login identity is registered under a different key

- **Reproduction:** Create `alice`, then send the handler a successful login request with username `"  alice  "`. Capture `state.CLIENTS` while the login response is sent.
- **Current behavior:** Authentication trims the name and succeeds, but the handler uses the untrimmed request value as the connection-registry key.
- **Desired behavior:** The connection registry must use the authenticated normalized username, `alice`.
- **Affected test:** `tests/integration/test_server_accounts.py::test_login_registers_the_normalized_username`

## BUG-SERVER-002 — Missing signup passwords silently use a default

- **Reproduction:** Send a signup request containing a username but no password field.
- **Current behavior:** The handler supplies `"123"`, creates the account, and returns `signup_response`.
- **Desired behavior:** Signup must reject a request that omits its password.
- **Affected test:** `tests/integration/test_server_accounts.py::test_signup_rejects_a_request_without_password`

## BUG-SERVER-003 — Sender claims are not bound to the registered socket

- **Reproduction:** Register `bob` with one fake socket and a connected recipient with another. Invoke `messaging.receive` through Bob's socket with a valid Alice token and a payload claiming `sender: "alice"`.
- **Current behavior:** `receive` registers the received socket under Alice before authentication and sends Alice's message to the recipient.
- **Desired behavior:** The server must reject a sender claim when the received socket belongs to a different registered user, without delivery or connection-registry mutation.
- **Affected test:** `tests/integration/test_server_messaging.py::test_receive_rejects_sender_claim_from_a_different_registered_socket`

## BUG-SERVER-004 — `manage_room` handler dispatch has the wrong arity

- **Reproduction:** Register Alice's fake socket, then pass a `manage_room` frame through `Server.handler` with a room ID, username, and token.
- **Current behavior:** The dispatcher calls `manage_room(websocket, room_id, uid, token)` although the handler accepts only `(websocket, room_id, uid)`. The resulting `TypeError` is caught by the outer handler and no room response is sent.
- **Desired behavior:** The dispatched action must join the room and return the normal successful `room_response`.
- **Affected test:** `tests/integration/test_server_messaging.py::test_manage_room_action_joins_and_acknowledges_through_handler_dispatch`

## BUG-SERVER-005 — Rejected message authentication replaces connection state

- **Reproduction:** Register `victim` with a victim fake socket, then invoke `messaging.receive` through a distinct attacker socket with `sender: "victim"` and an invalid token.
- **Current behavior:** Before authentication is checked, `receive` overwrites `CLIENTS["victim"]` with the attacker socket while preserving the victim's rooms and timestamp deque. It then returns `{"error": "Auth failed"}`.
- **Desired behavior:** A request that fails authentication must not create, replace, or mutate an authenticated connection mapping.
- **Affected test:** `tests/integration/test_server_abuse.py::test_rejected_authentication_does_not_replace_a_victim_connection_mapping`

## BUG-SERVER-006 — Destination address is accepted as a credential

- **Reproduction:** Create a valid Alice token, use it as the message `address`, register a recipient under that address, and send with `token: "invalid"` while claiming Alice as sender.
- **Current behavior:** `receive` validates the address as an alternative token, delivers to that recipient, and returns a success acknowledgement despite the invalid designated token field.
- **Desired behavior:** Only the designated `token` field may authenticate a request; destination data must never substitute for credentials.
- **Affected test:** `tests/integration/test_server_abuse.py::test_receive_requires_the_designated_token_field_not_a_token_in_address`

## BUG-CLIENT-001 — Stale acknowledgements are consumed as later control responses

- **Reproduction:** Put a normal `{"action": "ack"}` send acknowledgement and then a `{"action": "heartbeat"}` response into `ChatClient._control_queue`, then call `heartbeat`.
- **Current behavior:** `heartbeat` returns the stale acknowledgement because every control method takes the next FIFO packet without checking its action.
- **Desired behavior:** A control operation must consume only its own response, leaving unrelated queued packets available for their appropriate consumer.
- **Affected test:** `tests/unit/test_client_controls.py::test_heartbeat_does_not_consume_a_stale_send_acknowledgement`

## BUG-CLIENT-002 — Login accepts unrelated token-bearing responses

- **Reproduction:** Put `{"action": "signup_response", "token": "unrelated-token"}` into `ChatClient._control_queue`, then call `login`.
- **Current behavior:** `login` treats any response containing a `token` as successful, stores it, and sets the requested username.
- **Desired behavior:** Login must accept only the expected login response shape/action and reject unrelated token-bearing packets.
- **Affected test:** `tests/unit/test_client_controls.py::test_login_rejects_an_unrelated_token_bearing_response`

## BUG-CLIENT-003 — Message-handler exceptions terminate the listener

- **Reproduction:** Configure a message handler that raises, then feed the listener two valid direct-message `receive` packets.
- **Current behavior:** The first message is saved, then the callback exception escapes `_listen_loop`; the second packet is never received or saved.
- **Desired behavior:** A callback failure must be isolated so the listener can continue processing subsequent incoming packets.
- **Affected test:** `tests/unit/test_client_listener.py::test_callback_exception_does_not_stop_later_incoming_messages`
