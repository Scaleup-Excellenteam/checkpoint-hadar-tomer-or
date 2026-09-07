### Phase handoff

* Completed phase: Phase 7 — Client history and incoming-message processing.
* Commit/revision and working-tree status: Base revision `3602488`; working tree contains the approved Phase 6 test/documentation changes plus Phase 7 additions. No production files changed.
* Changed test/config files: `tests/integration/test_client_history.py`, `tests/unit/test_client_listener.py`, `tests/KNOWN_ISSUES.md`, `tests/PHASE_7_HANDOFF.md`.
* Verification commands and results:

  * Focused: `./.venv/Scripts/python.exe -m pytest -q -ra tests/integration/test_client_history.py tests/unit/test_client_listener.py` — 20 passed, 1 xfailed.
  * Cumulative: `./.venv/Scripts/python.exe -m pytest -q -ra` — 91 passed, 10 xfailed, 36 pre-existing JWT key-length warnings.
* Manual review: pending.

### Reusable context

* Fixtures/helpers added: `history_client` opens a real user-scoped SQLite database beneath `tmp_path`; listener tests reuse Phase 6 `client_factory` and `FakeConnection`, with `run_scripted_listener` feeding decoded packets without threads.
* Temporary SQLite strategy: explicit paths are always under `tmp_path`; default-path coverage changes cwd to `tmp_path`. Clients close their connection in fixture teardown, and reopen tests use fresh SQLite connections.
* Listener fake/script strategy: `_raw_recv` is replaced by a finite iterator for classification tests; `_raw_recv` itself is exercised with scripted raw JSON frames.
* Thread strategy: Phase 6 `InertThread` remains active for every constructed client. No background listener runs.
* Cleanup requirements: close every client/history connection; direct SQLite verification connections are explicitly closed.
* Confirmed history schema/row format: `messages(id, chat_id, sender, direction, message, timestamp)`; retrieval returns `(chat_id, sender, direction, message, timestamp)` tuples. Timestamps are UTC ISO-8601 strings.
* Confirmed outgoing-history semantics: a successful local `send` immediately inserts a `sent` row keyed by the requested/current target; send errors and false precondition paths create no row. Empty, Unicode, and SQL-looking messages store verbatim.
* Confirmed incoming direct-message behavior: `receive` addressed to the logged-in username stores a `received` row/callback chat ID equal to the sender.
* Confirmed room-message behavior: a `receive` addressed to another identifier stores and reports that address as chat ID, preserving the sender; thus room and direct keys remain separate.
* Confirmed control-packet classification: representative ack, auth/logout/room/heartbeat responses, and an error packet go only to `_control_queue`, not history.
* Confirmed callback ordering: history save precedes callback invocation.

### Outstanding items

* Known-defect IDs: retained `BUG-AUTH-001`, `BUG-SERVER-001` through `BUG-SERVER-006`, `BUG-CLIENT-001`, and `BUG-CLIENT-002`; added `BUG-CLIENT-003`.
* Affected tests: `tests/unit/test_client_listener.py::test_callback_exception_does_not_stop_later_incoming_messages` for the new defect.
* Strict xfail reasons: `BUG-CLIENT-003` — callback exceptions escape `_listen_loop` and stop later reception. Existing nine strict xfails remain unchanged.
* Unresolved listener/history contract questions: negative `get_history(limit=...)` behavior was intentionally not specified or tested. `_raw_recv` returns non-object JSON values, while `_listen_loop` then raises `AttributeError`; broader malformed-input policy is deferred to Phase 8. Listener handling of SQLite write failure is also deferred.
* Any production changes: none.

### Next session

* Next approved phase: Phase 8 — Malformed input, fault containment, and sensitive output, only after manual approval.
* Files to read: `plan.md`, this handoff, `tests/conftest.py`, `tests/KNOWN_ISSUES.md`, `client.py`, `tests/integration/test_client_history.py`, and `tests/unit/test_client_listener.py`.
* Fixtures/helpers Phase 8 should reuse: Phase 6 `client_factory`, `FakeConnection`, `InertThread`; Phase 7 `history_client` and `run_scripted_listener` where their scope fits.
* Prerequisites/deviations from plan: use real SQLite only when persistence matters; preserve all ten strict xfails unless separately fixed; no Phase 8 production work has started.
