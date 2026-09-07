# Known issues

## BUG-AUTH-001 — Expired JWTs remain valid while present in memory

- **Reproduction:** Create a correctly signed token whose `exp` claim is in the past, add it to `AuthManager.sessions` for its user, then call `validate_user_token`.
- **Current behavior:** `validate_user_token` returns `True` because it only checks the in-memory token-to-user mapping and never decodes or validates JWT claims.
- **Desired behavior:** An expired token must be rejected even if it remains in the session map.
- **Affected test:** `tests/integration/test_auth.py::test_validate_user_token_rejects_an_expired_signed_token`
