# Known issues

## BUG-AUTH-001 — Expired JWTs remain valid while present in memory

- **Reproduction:** Create a correctly signed token whose `exp` claim is in the past, add it to `AuthManager.sessions` for its user, then call `validate_user_token`.
- **Status:** Resolved. The regression is now a normal passing test.
- **Previous behavior:** `validate_user_token` returned `True` because it only checked the in-memory token-to-user mapping and never decoded or validated JWT claims.
- **Fix:** Require an active session for the requested user plus a JWT verified with the existing secret and explicit project algorithm. Require `exp` and `username`, enforce expiration and signed username matching, and return `False` on JWT validation errors. Validation leaves sessions unchanged.
- **Desired behavior:** An expired token must be rejected even if it remains in the session map.
- **Affected test:** `tests/integration/test_auth.py::test_validate_user_token_rejects_an_expired_signed_token`
