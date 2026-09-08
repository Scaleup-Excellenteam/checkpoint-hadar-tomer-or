import pytest


@pytest.mark.unit
def test_hash_password_is_deterministic_with_salt_and_does_not_return_plaintext(
    auth_manager_factory,
):
    manager = auth_manager_factory()
    fixed_salt = b"test_salt_123456"

    # Deterministic when using the same salt
    hash1 = manager.hash_password("secret phrase", fixed_salt)
    hash2 = manager.hash_password("secret phrase", fixed_salt)
    assert hash1 == hash2

    # Verification passes for correct password and fails for incorrect
    assert manager.verify_password("secret phrase", hash1) is True
    assert manager.verify_password("wrong phrase", hash1) is False
    assert hash1 != "secret phrase"

    # Auto-generated salts are unique per invocation
    auto_hash1 = manager.hash_password("secret phrase")
    auto_hash2 = manager.hash_password("secret phrase")
    assert auto_hash1 != auto_hash2
    assert manager.verify_password("secret phrase", auto_hash1) is True
    assert manager.verify_password("secret phrase", auto_hash2) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sender", "address", "expected"),
    [
        ("alice", "", False),
        ("alice", "alice", False),
        ("alice", "bob", True),
    ],
)
def test_validate_user_address_matches_current_address_rules(
    auth_manager_factory, sender, address, expected
):
    manager = auth_manager_factory()

    assert manager.validate_user_address(sender, address) is expected
