### Phase handoff

* Completed phase: Phase 6 — Client requests and control-response handling.
* Commit/revision and working-tree status: `3602488`; modified `tests/KNOWN_ISSUES.md`, added `tests/unit/test_client_controls.py` and this handoff. No production files changed.
* Changed test/config files: `tests/unit/test_client_controls.py`, `tests/KNOWN_ISSUES.md`, `tests/PHASE_6_HANDOFF.md`.
* Verification commands and results:

  * Focused: `./.venv/Scripts/python.exe -m pytest -q -ra tests/unit/test_client_controls.py` — 14 passed, 2 xfailed.
  * Cumulative: `./.venv/Scripts/python.exe -m pytest -q -ra` — 71 passed, 9 xfailed, 36 pre-existing JWT key-length warnings.
* Manual review: pending.

### Reusable context

* Fixtures/helpers added: `client_factory`, `FakeConnection`, `InertThread`, `EmptyControlQueue`, `FakeHistory`, and `sent_json` in `tests/unit/test_client_controls.py`.
* Fake connection behavior: records raw JSON strings in `sent`, can raise a configured exception from `send`, and tracks `close`.
* Queue/timeout helper behavior: normal flows preload the real production `queue.Queue`; `EmptyControlQueue.get(timeout=5)` immediately raises `queue.Empty`, with no sleeps.
* Thread-isolation strategy: patch `client.connect`, `ssl.create_default_context`, and `threading.Thread` before constructing `ChatClient`; `InertThread.start` records startup but never runs `_listen_loop`.
* History stubs used: `_open_history_db` and `_save_history` are patched only for method-level assertions; `FakeHistory` verifies close paths without touching SQLite.
* Confirmed outbound client protocol: signup/login send `{action, payload: {username, password}}`; logout sends `{action: logout, token}`; heartbeat sends `{action: heartbeat}`; join room sends `{action: join_room, room_id, uid}`; send sends `{action: send, token, payload: {sender, address, message}}`.
* Confirmed client state-transition behavior: signup success does not authenticate locally; login stores the requested username and response token then opens history; logout clears auth/target and closes history only after `logout_response`; successful `room_response` with `payload.status == success` sets the target; `start_chat` is local.
* Confirmed `send_message` semantics: `True` means the JSON send call returned and the client recorded a local outgoing-history attempt; it does not await or validate the server acknowledgement. Missing token/target returns `False`; send exceptions propagate before history save.

### Outstanding items

* Known-defect IDs: retained `BUG-AUTH-001`, `BUG-SERVER-001` through `BUG-SERVER-006`; added `BUG-CLIENT-001` and `BUG-CLIENT-002`.
* Affected tests: the seven existing strict xfails; `test_heartbeat_does_not_consume_a_stale_send_acknowledgement`; `test_login_rejects_an_unrelated_token_bearing_response`.
* Strict xfail reasons: `BUG-CLIENT-001` is stale acknowledgement/control-packet FIFO contamination; `BUG-CLIENT-002` is accepting an unrelated token-bearing packet as a login response.
* Unresolved client/protocol questions: no protocol correlation ID exists; behavior for preserving/re-routing unrelated control packets must be decided when production work is approved. Heartbeat currently returns any dequeued packet, including error packets, rather than interpreting success/failure.
* Any production changes: none.

### Next session

* Next approved phase: Phase 7 — Client history and incoming-message processing, only after manual approval.
* Files to read: `plan.md`, this handoff, `tests/conftest.py`, `tests/KNOWN_ISSUES.md`, `client.py`, and `tests/unit/test_client_controls.py`.
* Fixtures/helpers Phase 7 should reuse: `client_factory`, `FakeConnection`, and `InertThread`; replace history method stubs with temporary real SQLite databases only for Phase 7 persistence scope.
* Prerequisites/deviations from plan: retain all nine strict xfails unless production code is separately fixed. Phase 6 intentionally did not test `_listen_loop`, incoming-message routing, callback execution, history rows, TLS, or real networking.
