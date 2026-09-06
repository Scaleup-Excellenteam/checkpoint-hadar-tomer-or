from dataclasses import dataclass
from hashlib import new
import sqlite3
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
        self.db = sqlite3.connect("users.db", check_same_thread=False)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL
            )
        """)

        self.db.commit()

        # token -> username
        self.sessions = {}


    def hash_password(self, password: str) -> str:
        return new("sha256", password.encode()).hexdigest()


    def signup(self, username: str, password: str):

        if not username or not password:
            return False

        username = username.strip()
        password = password.strip()

        if not username or not password:
            return False

        password_hash = self.hash_password(password)

        user = self.db.execute(
            "SELECT username FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if user:
            return False

        self.db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )

        self.db.commit()

        return True


    def login(self, username: str, password: str):

        if not username or not password:
            return False

        username = username.strip()
        password = password.strip()

        password_hash = self.hash_password(password)

        user = self.db.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if not user:
            return False

        if password_hash != user[0]:
            return False

        token = jwt.encode(
            {
                "username": username,
                "exp": datetime.now(timezone.utc) + timedelta(hours=1)
            },
            SECRET_KEY,
            algorithm=ALGORITHM
        )

        self.sessions[token] = username

        return token


    def validate_user_token(self, user: str, token: str):

        if token not in self.sessions:
            return False

        if self.sessions[token] != user:
            return False

        return True


    def validate_user_address(self, sender: str, address: str):

        if not address:
            return False

        if address == sender:
            return False

        return True


    def logout(self, token: str):

        if token in self.sessions:
            del self.sessions[token]
            return True

        return False