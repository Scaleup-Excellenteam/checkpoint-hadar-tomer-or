import pytest


@pytest.mark.unit
def test_internal_message_round_trips_to_and_from_a_dictionary(isolated_server_import):
    models = isolated_server_import("Server.models")
    message = models.InternalMessage(
        sender="tomer",
        address="room-\u05e9\u05dc\u05d5\u05dd",
        message="Hello \U0001f44b",
    )

    serialized = message.to_dict()

    assert serialized == {
        "sender": "tomer",
        "address": "room-\u05e9\u05dc\u05d5\u05dd",
        "message": "Hello \U0001f44b",
    }
    assert models.InternalMessage.from_dict(serialized) == message


@pytest.mark.unit
def test_internal_message_preserves_empty_strings(isolated_server_import):
    models = isolated_server_import("Server.models")

    assert models.InternalMessage.from_dict(
        {"sender": "", "address": "", "message": ""}
    ) == models.InternalMessage("", "", "")


@pytest.mark.unit
@pytest.mark.parametrize("missing_key", ["sender", "address", "message"])
def test_internal_message_requires_every_serialized_field(
    isolated_server_import, missing_key
):
    models = isolated_server_import("Server.models")
    data = {"sender": "alice", "address": "bob", "message": "hi"}
    del data[missing_key]

    with pytest.raises(KeyError):
        models.InternalMessage.from_dict(data)


@pytest.mark.unit
def test_internal_message_ignores_unrecognized_serialized_fields(isolated_server_import):
    models = isolated_server_import("Server.models")

    message = models.InternalMessage.from_dict(
        {
            "sender": "alice",
            "address": "bob",
            "message": "hi",
            "delivery_id": "unused-by-current-protocol",
        }
    )

    assert message == models.InternalMessage("alice", "bob", "hi")
