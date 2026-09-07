### Phase handoff

* Completed phase: Phase 2 — Accounts, tokens, and reputation persistence.
* Commit/revision and working-tree status: `04afe3f`; Phase 2 changes are uncommitted. `plan.md` remains ignored.
* Changed test/config files: `tests/conftest.py`, `tests/unit/test_auth_helpers.py`, `tests/integration/test_auth.py`, `tests/KNOWN_ISSUES.md`, `tests/PHASE_2_HANDOFF.md`.
* Verification commands and results:

  * Focused: `16 passed, 1 xfailed, 8 warnings in 0.51s` — `./.venv/Scripts/python.exe -m pytest -q -ra tests/unit/test_auth_helpers.py tests/integration/test_auth.py`
  * Cumulative: `25 passed, 1 xfailed, 8 warnings in 0.63s` — `./.venv/Scripts/python.exe -m pytest -q -ra`
* Manual review: pending

### Reusable context

* Fixtures/helpers added: `auth_manager_factory` in `tests/conftest.py` creates one or more `AuthManager` instances against the same `tmp_path/users.db`.
* Cleanup requirements: The fixture closes every SQLite connection during teardown; tests that close a manager early are tolerated by its guarded cleanup. Do not instantiate `AuthManager` outside this fixture unless the current directory is isolated first.
* Runtime/setup changes: None. The existing Phase 1 Python 3.12.12 environment remains in use.
* Confirmed authentication behavior needed by Phase 3: Signup and login strip outer credential whitespace; successful login creates a signed JWT and records only an in-memory token-to-username session; logout removes that mapping. Accounts and reputation persist in SQLite; sessions do not survive a fresh `AuthManager`.

### Outstanding items

* Known-defect IDs: `BUG-AUTH-001`.
* Affected tests: `tests/integration/test_auth.py::test_validate_user_token_rejects_an_expired_signed_token`.
* Strict xfail reasons: `BUG-AUTH-001: validate_user_token accepts expired JWTs stored in sessions`.
* Unresolved contract questions: Expired tokens remain valid while their session-map entry exists. PyJWT also warns that the current hardcoded HS256 signing key is below its recommended 32-byte minimum; no production or test-policy change was made in this phase.
* Any production changes: none.

### Next session

* Next approved phase: Phase 3 — Server authentication and control protocol, only after manual approval.
* Files to read: `plan.md`, `tests/PHASE_1_HANDOFF.md`, `tests/PHASE_2_HANDOFF.md`, `tests/conftest.py`, `tests/KNOWN_ISSUES.md`, `auth.py`, `Server/Server.py`, and `Server/state.py`.
* Prerequisites/deviations from plan: Run the cumulative suite and complete manual Phase 2 review before beginning Phase 3. Retain the strict xfail unless production JWT-expiry validation is separately fixed.
