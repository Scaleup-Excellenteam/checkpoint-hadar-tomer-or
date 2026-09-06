from dataclasses import dataclass
from hashlib import new
import jwt
from datetime import datetime, timedelta, timezone

SECRET_KEY = "my-super-secret-key"
ALGORITHM = "HS256"


@dataclass
class User:
    username: str
    password_hash: str


class AuthManager:
    def __init__(self):
        # username -> User
        self.users = {}

        # token -> username
        self.sessions = {}

    def hash_password(self, password: str) -> str:
        """
        Hash a password with salt.
        """
        return new("sha256", password.encode()).hexdigest()

    def signup(self, username: str, password: str):
        """
        Create a new user.
        """
        if not username or not password:
            return False

        username = username.strip()
        password = password.strip()
        password_hash = self.hash_password(password)

        if not username or not password:
            return False

        if username in self.users:
            return False

        self.users[username] = User(username=username, password_hash=password_hash)
        return True

    def login(self, username: str, password: str):
        """
        Authenticate a user.
        Return:
            token on success
            failure otherwise
        """
        if not username or not password:
            return False
        username = username.strip()
        password = password.strip()
        password_hash = self.hash_password(password)

        if username not in self.users:
            return False
        if password_hash != self.users[username].password_hash:
            return False
        token = jwt.encode(
            {
                "username": username,
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        self.sessions[token] = username
        return token

    def validate_user_token(self, user: str, token: str):
        """
        Check whether a token represents an authenticated user.

        TODO:
        - Find token in active sessions
        - Return the username if valid
        - Reject invalid token
        """
        if token not in self.sessions:
            return False
        if self.sessions[token] != user:
            return False
        return True

    def logout(self, token: str):
        """
        Invalidate an existing session.

        TODO:
        - Remove token from active sessions
        """
        if token in self.sessions:
            del self.sessions[token]
            return True
        return False
