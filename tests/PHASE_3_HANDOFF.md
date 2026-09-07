### Phase handoff

* Completed phase: Phase 3 — Server authentication and control protocol.
* Commit/revision and working-tree status: `c938246`; Phase 3 changes are uncommitted. `plan.md` remains ignored.
* Changed test/config files: `tests/conftest.py`, `tests/integration/test_server_accounts.py`, `tests/KNOWN_ISSUES.md`, `tests/PHASE_3_HANDOFF.md`.
* Verification commands and results:

  * Focused: `11 passed, 2 xfailed, 6 warnings in 0.55s` — `./.venv/Scripts/python.exe -m pytest -q -ra tests/integration/test_server_accounts.py`
  * Cumulative: `36 passed, 3 xfailed, 14 warnings in 1.04s` — `./.venv/Scripts/python.exe -m pytest -q -ra`
* Manual review: pending

### Reusable context

* Fixtures/helpers added: `isolated_server_module` in `tests/conftest.py`; `FakeWebSocket` in `tests/integration/test_server_accounts.py`.
* Fake socket/transport behavior: Accepts a finite list of raw incoming frames as an async iterator, parses and captures JSON passed to `send`, records `close`, and optionally calls an `on_send` callback. The callback captures server state at the observable point a response is sent.
* Cleanup requirements: `isolated_server_module` clears `CLIENTS` and `ROOMS`, closes `state.auth.db`, and unloads `Server` modules after each test. The fake transport creates no tasks or sockets.
* Server import isolation: The fixture changes to `tmp_path`, replaces only `ssl.SSLContext` certificate loading and `logger.setup_logger` during import, then restores both through `monkeypatch`. `Server.Server` therefore creates `users.db` only in `tmp_path`.
* Confirmed server control-protocol behavior needed by Phase 4: Signup issues a token but does not register `CLIENTS`. Login registers a socket before `login_response`; normal handler completion removes that mapping. Heartbeat ignores authentication fields and returns `{"action": "heartbeat"}`. Logout always returns success and closes the socket, including for invalid tokens, then handler cleanup removes any matching connection.

### Outstanding items

* Known-defect IDs: `BUG-AUTH-001`, `BUG-SERVER-001`, `BUG-SERVER-002`.
* Affected tests: `test_validate_user_token_rejects_an_expired_signed_token`, `test_login_registers_the_normalized_username`, and `test_signup_rejects_a_request_without_password`.
* Strict xfail reasons: Expired in-memory JWTs remain accepted; successful whitespace-padded login registers the untrimmed connection key; missing signup passwords are replaced with `"123"`.
* Unresolved contract questions: Login also supplies `"123"` when password is omitted, but this phase records the signup defect only. The existing short HS256 signing-key warning remains unchanged.
* Any production changes: none.

### Next session

* Next approved phase: Phase 4 — Direct delivery, rooms, and acknowledgements, only after manual approval.
* Files to read: `plan.md`, `tests/PHASE_2_HANDOFF.md`, `tests/PHASE_3_HANDOFF.md`, `tests/conftest.py`, `tests/KNOWN_ISSUES.md`, `Server/Server.py`, `Server/messaging.py`, and `Server/state.py`.
* Fixtures/helpers Phase 4 should reuse: `isolated_server_module` for temporary state/authentication and `FakeWebSocket` as a model for recipient and sender fake sockets; extend it only if delivery tests require a narrowly scoped send failure.
* Prerequisites/deviations from plan: Retain all three strict xfails unless a separately approved production fix lands. Phase 4 must avoid changing Phase 3 control-protocol assertions and should not start rate-limit coverage.
