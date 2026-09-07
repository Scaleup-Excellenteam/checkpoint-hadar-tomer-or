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
        # reputation persists with user
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                reputation TINYINT NOT NULL DEFAULT 0
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

        return self.sessions[token] == user


    def validate_user_address(self, sender: str, address: str):

        if not address:
            return False
    
        return address != sender


    def logout(self, token: str):

        if token in self.sessions:
            del self.sessions[token]
            return True

        return False


    def get_reputation(self, token: str):
        """
        This function returns the reputation of a user connected to the given token.

        token - the JWT connected to the user
        returns user score or -200 if the token is invalid or user not found.
        rep field uses tiny int, so it has a -128/127 range or 0-255, so -200 is a clear indicator.
        """
        if token not in self.sessions:
            return -200 #
        username = self.sessions[token]
        row = self.db.execute("SELECT reputation FROM users WHERE username = ?", (username,)).fetchone()
        return row[0] if row else -200



    def update_reputation(self, token: str, rep_change: int):
        """
        This function updates the reputation of a user connected to the given token, by rep_change points.
        token - the JWT connected to the user
        rep_change - the reputation of the user connected to the given token, positive or negative.
        """
        if token not in self.sessions:
            return False
        username = self.sessions[token]
        self.db.execute("UPDATE users SET reputation = reputation + ? WHERE username = ?",(rep_change,username))
        self.db.commit()
        return True