import pytest


@pytest.mark.unit
def test_hash_password_is_deterministic_and_does_not_return_plaintext(
    auth_manager_factory,
):
    manager = auth_manager_factory()

    password_hash = manager.hash_password("secret phrase")

    assert password_hash == manager.hash_password("secret phrase")
    assert password_hash != "secret phrase"


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
