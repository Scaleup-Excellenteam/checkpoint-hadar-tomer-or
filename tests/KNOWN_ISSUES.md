# Known issues

## BUG-AUTH-001 — Expired JWTs remain valid while present in memory

- **Reproduction:** Create a correctly signed token whose `exp` claim is in the past, add it to `AuthManager.sessions` for its user, then call `validate_user_token`.
- **Current behavior:** `validate_user_token` returns `True` because it only checks the in-memory token-to-user mapping and never decodes or validates JWT claims.
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
