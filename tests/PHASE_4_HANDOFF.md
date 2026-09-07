### Phase handoff

* Completed phase: Phase 4 — Direct delivery, rooms, and acknowledgements.
* Commit/revision and working-tree status: `c4bc8c6`; uncommitted changes are `tests/KNOWN_ISSUES.md` and `tests/integration/test_server_messaging.py` (plus this handoff).
* Changed test/config files: `tests/integration/test_server_messaging.py`, `tests/KNOWN_ISSUES.md`, `tests/PHASE_4_HANDOFF.md`.
* Verification commands and results:

  * Focused: `12 passed, 2 xfailed, 12 warnings in 0.67s` — `./.venv/Scripts/python.exe -m pytest -q -ra tests/integration/test_server_messaging.py`
  * Cumulative: `48 passed, 5 xfailed, 26 warnings in 1.46s` — `./.venv/Scripts/python.exe -m pytest -q -ra`
* Manual review: pending

### Reusable context

* Fixtures/helpers added: `FakeRecipientSocket`, `FakeHandlerSocket`, `authenticated_user`, and `message_frame` in `tests/integration/test_server_messaging.py`; existing `isolated_server_module` remains the per-test server/state isolation fixture.
* Recipient fake-socket behavior: Captures decoded JSON sent through `send`, counts delivery attempts, and can raise a `RuntimeError` from `send`. `FakeHandlerSocket` adds a finite async incoming-frame iterator and an optional send callback.
* Cleanup requirements: Use `isolated_server_module` for every server test. It clears `CLIENTS` and `ROOMS`, closes the temporary auth database, and unloads server modules. The fake sockets create no tasks or network resources.
* Confirmed direct-message contract: Successful delivery sends `{"action": "receive", "payload": {"sender", "address", "message"}}` to the recipient, then `{"action": "ack", "payload": {"status": "success"}}` to the sender. Unicode, empty messages, and self-delivery are currently allowed. Missing recipients and recipient send failures return errors.
* Confirmed room contract: `manage_room` directly creates rooms, joins members once, and records membership in both registries. `join_room` reaches this functioning path. Room sends exclude the sender, fan out to all remaining members, and report failure for an empty/sender-only room or any partial delivery failure, while still attempting other recipients.
* Confirmed acknowledgement contract: The sole success acknowledgement is `{"action": "ack", "payload": {"status": "success"}}`; it has no message/delivery ID, timestamp, receipt, or persistence meaning.
* Address-resolution behavior needed later: `messaging.receive` resolves a room before a connected username when the same address exists in both registries.

### Outstanding items

* Known-defect IDs: `BUG-AUTH-001`, `BUG-SERVER-001`, `BUG-SERVER-002`, `BUG-SERVER-003`, `BUG-SERVER-004`.
* Affected tests: Existing Phase 2/3 strict xfails, plus `test_receive_rejects_sender_claim_from_a_different_registered_socket` and `test_manage_room_action_joins_and_acknowledges_through_handler_dispatch`.
* Strict xfail reasons: Expired in-memory JWT acceptance; whitespace-keyed login connections; signup's default password; sender claims not bound to their received socket; and four-argument `manage_room` dispatch to a three-argument handler.
* Unresolved room/security contract questions: Room membership is not required to send to a room, and rooms are not persistent. The socket-identity regression shows a registered socket can claim another authenticated sender; do not broaden into token/address bypass coverage until Phase 5.
* Any production changes: none.

### Next session

* Next approved phase: Phase 5 — Server rate limiting and authentication boundaries, only after manual approval.
* Files to read: `plan.md`, `tests/PHASE_3_HANDOFF.md`, `tests/PHASE_4_HANDOFF.md`, `tests/conftest.py`, `tests/KNOWN_ISSUES.md`, `Server/messaging.py`, and `Server/state.py`.
* Fixtures/helpers Phase 5 should reuse: `isolated_server_module`, `FakeRecipientSocket`, `authenticated_user`, and `message_frame` from Phase 4.
* Prerequisites/deviations from plan: Retain all five strict xfails unless production code is separately fixed. Phase 4 deliberately did not test rate-limit boundaries, reputation deductions, token/address authentication bypasses, or real transport.
