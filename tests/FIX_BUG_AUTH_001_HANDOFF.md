### Fix handoff

* Bug fixed: BUG-AUTH-001 — Expired JWTs remain valid while present in memory.
* Root cause: `validate_user_token(user, token)` checked only the in-memory token-to-user mapping; it never verified the signed JWT or expiration.
* Production files changed: `auth.py`, confined to `validate_user_token` (plus final newline normalization).
* Test files changed: `tests/integration/test_auth.py`. Documentation: `tests/KNOWN_ISSUES.md` and this handoff.
* Exact fix: Keep the active-session and requested-user checks, then call `jwt.decode` with the existing secret, `algorithms=[ALGORITHM]` (HS256), and required `exp` and `username` claims. Return `False` for `jwt.InvalidTokenError`, and accept only when the verified username matches the requested/session user. Login already generates these claims; token schema, method argument order, and signing configuration are unchanged. Validation does not mutate sessions.
* Regression test result: Before production edits, `./.venv/Scripts/python.exe -m pytest -q --runxfail tests/integration/test_auth.py::test_validate_user_token_rejects_an_expired_signed_token` failed because validation returned `True` instead of `False`. After the fix, the regression passes normally in the focused and cumulative suites; its BUG-AUTH-001 xfail marker was removed.
* Focused suite result: `./.venv/Scripts/python.exe -m pytest -q -ra tests/unit/test_auth_helpers.py tests/integration/test_auth.py` — 26 passed, 24 warnings.
* Cumulative suite result: `./.venv/Scripts/python.exe -m pytest -q -ra` — 101 passed, 9 xfailed, 71 warnings. No unexpected failures, skips, or XPASS. Warnings concern the existing short signing key; additional JWT decoding and focused cases increase their count.
* Remaining xfails: BUG-SERVER-001 through BUG-SERVER-006, and BUG-CLIENT-001 through BUG-CLIENT-003. All unrelated markers and tests remain unchanged.
* `tests/KNOWN_ISSUES.md` update: BUG-AUTH-001 marked resolved, with its previous behavior and exact fix retained for reference.
* Any related issue discovered but intentionally not fixed: `get_reputation()` and `update_reputation()` independently trust session membership without JWT validation. This remains a possible separate issue; neither method was changed. Expired-session cleanup remains deferred.
* Working-tree status: Started clean at revision `f540628`. Uncommitted changes: modified `auth.py`, `tests/integration/test_auth.py`, `tests/KNOWN_ISSUES.md`; added this handoff. No commit created. `git diff --check` passed before handoff creation.

Focused coverage uses a fixed JWT validation clock and numeric expiration timestamps, real signing/verification, and temporary SQLite through `auth_manager_factory`. Added cases cover valid active tokens, valid tokens without sessions, malformed tokens stored in sessions, invalid signatures, a non-project algorithm, missing expiration/username, mismatched signed username, and the exact expiration boundary. The original expired-token regression also asserts session preservation. Existing tests continue covering logout revocation, wrong requested user, and rejection after AuthManager restart. No sleeps or network connections are used.

Only BUG-AUTH-001 was addressed. Phase 8 and subsequent defect fixes have not begun.
