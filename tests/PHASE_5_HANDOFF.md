### Phase handoff

* Completed phase: Phase 5 — Server rate limiting and authentication boundaries.
* Commit/revision and working-tree status: `c4bc8c6`; Phase 5 changes are uncommitted: `tests/integration/test_server_abuse.py` and `tests/KNOWN_ISSUES.md` (plus this handoff). Prior Phase 4 files, `tests/integration/test_server_messaging.py` and `tests/PHASE_4_HANDOFF.md`, also remain uncommitted.
* Changed test/config files: `tests/integration/test_server_abuse.py`, `tests/KNOWN_ISSUES.md`, `tests/PHASE_5_HANDOFF.md`.
* Verification commands and results:

  * Focused: `9 passed, 2 xfailed, 10 warnings in 0.52s` — `./.venv/Scripts/python.exe -m pytest -q -ra tests/integration/test_server_abuse.py`
  * Cumulative: `57 passed, 7 xfailed, 36 warnings in 1.77s` — `./.venv/Scripts/python.exe -m pytest -q -ra`
* Manual review: pending

### Reusable context

* Fixtures/helpers added: `FakeClock` and `register_self` in `tests/integration/test_server_abuse.py`. The Phase 4 `FakeRecipientSocket`, `authenticated_user`, and `message_frame` are imported from `test_server_messaging`.
* Deterministic clock behavior: `FakeClock` returns its explicit mutable `value` and is patched over `server.messaging.time.monotonic`; no sleeps or wall-clock assumptions are used. The key tested timestamps are `100.0`, `130.0`, and `130.001`.
* Cleanup requirements: Every test uses `isolated_server_module`, which clears `CLIENTS`/`ROOMS`, closes the temporary auth database, and unloads server modules. Fake sockets do not start tasks or use network resources.
* Confirmed rate-limit contract: `MAX_MESSAGES` is 10 and `WINDOW_SECONDS` is 30. The first ten authenticated attempts are allowed; the next is rejected. Entries remain at exactly 30 seconds because removal uses `now - timestamp > 30`, then expire immediately after. Rejected attempts do not enter the deque. Authenticated sends to missing targets and failed recipient sockets do consume a budget entry.
* Confirmed reputation contract: Allowed attempts leave reputation unchanged. Each rate-limit rejection applies `SPAM_HIT` (`-5`) through the real temporary `AuthManager` and commits it to SQLite; repeated rejections deduct repeatedly. Users' deques and reputations are independent.
* Confirmed authentication-boundary behavior: Missing, random, revoked, and another user's tokens return only `{"error": "Auth failed"}` and do not deliver or consume a rate-limit timestamp when sent through the legitimate sender socket. Two distinct defects remain: invalid requests can replace an existing sender mapping before rejection, and a valid token placed in `address` authenticates a request whose `token` field is invalid.

### Outstanding items

* Known-defect IDs: `BUG-AUTH-001`, `BUG-SERVER-001`, `BUG-SERVER-002`, `BUG-SERVER-003`, `BUG-SERVER-004`, `BUG-SERVER-005`, `BUG-SERVER-006`.
* Affected tests: Existing Phase 2–4 strict xfails, plus `test_rejected_authentication_does_not_replace_a_victim_connection_mapping` and `test_receive_requires_the_designated_token_field_not_a_token_in_address`.
* Strict xfail reasons: Expired in-memory token acceptance; whitespace connection identity; default signup password; socket/sender identity mismatch; broken room dispatch arity; rejected-auth connection replacement; and address-as-token authentication.
* Unresolved security/contract questions: Room membership is still not required to send and rooms are nonpersistent. Phase 5 intentionally did not add room permissions, real transport, CAPTCHA/IP/distributed throttling, or expiry coverage beyond the retained `BUG-AUTH-001` regression.
* Any production changes: none.

### Next session

* Next approved phase: Phase 6 — Client requests and control-response handling, only after manual approval.
* Files to read: `plan.md`, `tests/PHASE_4_HANDOFF.md`, `tests/PHASE_5_HANDOFF.md`, `tests/conftest.py`, `tests/KNOWN_ISSUES.md`, `client.py`, and `Server/Server.py` as needed for protocol comparison.
* Fixtures/helpers Phase 6 should reuse: Existing server helpers only for protocol reference; Phase 6 should build its requested fake client connection/response-queue helpers separately. `FakeClock` is available if server limiter interactions become necessary later.
* Prerequisites/deviations from plan: Retain all seven strict xfails unless production code is separately fixed. Do not carry Phase 5 server authentication/rate-limit scope into client control-response tests except where their documented protocol shapes are relevant.
