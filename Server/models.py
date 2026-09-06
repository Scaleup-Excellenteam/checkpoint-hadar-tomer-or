from dataclasses import dataclass, asdict
from typing import Any, Dict

@dataclass
class InternalMessage:
    """
    Standardized internal message format (encapsulated in websocket message).
    sender - UID of Sender of the message.
    address - Address UID of the message, a user (group is a kind of user).
    message - Content of the message.
    """
    sender: str
    address: str
    message: str

    #return self as dict
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InternalMessage":
    #dict to class
        return cls(
            sender=data["sender"],
            address=data["address"],
            message=data["message"]
        )
