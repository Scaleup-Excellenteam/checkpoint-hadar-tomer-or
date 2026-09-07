from datetime import datetime, timedelta, timezone

import jwt
import pytest

from auth import ALGORITHM, SECRET_KEY


@pytest.mark.integration
@pytest.mark.security
def test_signup_trims_credentials_prevents_duplicates_and_never_stores_plaintext(
    auth_manager_factory,
):
    manager = auth_manager_factory()

    assert manager.signup("  alice  ", "  secret phrase  ") is True
    assert manager.signup("alice", "different password") is False

    stored_user = manager.db.execute(
        "SELECT username, password_hash, reputation FROM users WHERE username = ?", ("alice",)
    ).fetchone()

    assert stored_user == ("alice", manager.hash_password("secret phrase"), 0)
    assert stored_user[1] != "secret phrase"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("username", "password"),
    [("", "password"), ("alice", ""), ("   ", "password"), ("alice", "   ")],
)
def test_signup_rejects_empty_or_whitespace_only_credentials(
    auth_manager_factory, username, password
):
    manager = auth_manager_factory()

    assert manager.signup(username, password) is False


@pytest.mark.integration
def test_login_rejects_empty_unknown_and_incorrect_credentials(auth_manager_factory):
    manager = auth_manager_factory()
    assert manager.signup("alice", "correct password") is True

    assert manager.login("", "correct password") is False
    assert manager.login("alice", "") is False
    assert manager.login("unknown", "correct password") is False
    assert manager.login("alice", "wrong password") is False


@pytest.mark.integration
@pytest.mark.security
def test_login_returns_a_signed_token_for_the_trimmed_user(auth_manager_factory):
    manager = auth_manager_factory()
    assert manager.signup("alice", "correct password") is True

    token = manager.login("  alice  ", "  correct password  ")
    claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    assert manager.validate_user_token("alice", token) is True
    assert claims["username"] == "alice"
    assert claims["exp"] > datetime.now(timezone.utc).timestamp()


@pytest.mark.integration
def test_signup_and_login_support_sql_like_credentials(auth_manager_factory):
    manager = auth_manager_factory()
    username = "eve'); DROP TABLE users; --"
    password = "quote ' and semicolon;"

    assert manager.signup(username, password) is True
    assert manager.login(username, password)
    assert manager.db.execute("SELECT COUNT(*) FROM users").fetchone() == (1,)


@pytest.mark.integration
@pytest.mark.security
def test_token_validation_requires_the_logged_in_user_and_known_session(
    auth_manager_factory,
):
    manager = auth_manager_factory()
    assert manager.signup("alice", "password") is True
    assert manager.signup("bob", "password") is True
    alice_token = manager.login("alice", "password")
    bob_token = manager.login("bob", "password")

    assert manager.validate_user_token("alice", alice_token) is True
    assert manager.validate_user_token("bob", alice_token) is False
    assert manager.validate_user_token("alice", bob_token) is False
    assert manager.validate_user_token("alice", "unknown-token") is False


@pytest.mark.integration
@pytest.mark.security
def test_logout_revokes_the_session_token(auth_manager_factory):
    manager = auth_manager_factory()
    assert manager.signup("alice", "password") is True
    token = manager.login("alice", "password")

    assert manager.logout(token) is True
    assert manager.validate_user_token("alice", token) is False
    assert manager.logout(token) is False


@pytest.mark.integration
def test_reputation_is_updated_for_logged_in_user_and_invalid_tokens_are_rejected(
    auth_manager_factory,
):
    manager = auth_manager_factory()
    assert manager.signup("alice", "password") is True
    token = manager.login("alice", "password")

    assert manager.get_reputation(token) == 0
    assert manager.update_reputation(token, 7) is True
    assert manager.update_reputation(token, -2) is True
    assert manager.get_reputation(token) == 5
    assert manager.get_reputation("unknown-token") == -200
    assert manager.update_reputation("unknown-token", 5) is False


@pytest.mark.integration
@pytest.mark.security
def test_accounts_and_reputation_persist_but_sessions_do_not(auth_manager_factory):
    first_manager = auth_manager_factory()
    assert first_manager.signup("alice", "password") is True
    first_token = first_manager.login("alice", "password")
    assert first_manager.update_reputation(first_token, 12) is True
    first_manager.db.close()

    reopened_manager = auth_manager_factory()
    assert reopened_manager.validate_user_token("alice", first_token) is False
    reopened_token = reopened_manager.login("alice", "password")

    assert reopened_token
    assert reopened_manager.get_reputation(reopened_token) == 12


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.xfail(
    strict=True,
    reason="BUG-AUTH-001: validate_user_token accepts expired JWTs stored in sessions",
)
def test_validate_user_token_rejects_an_expired_signed_token(auth_manager_factory):
    manager = auth_manager_factory()
    assert manager.signup("alice", "password") is True
    expired_token = jwt.encode(
        {
            "username": "alice",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    manager.sessions[expired_token] = "alice"

    assert manager.validate_user_token("alice", expired_token) is False
