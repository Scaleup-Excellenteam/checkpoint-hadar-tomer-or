import os
from dataclasses import dataclass
import hmac
import hashlib
import sqlite3
import jwt
from datetime import datetime, timedelta, timezone


SECRET_KEY = "my-super-secret-key"
ALGORITHM = "HS256"
PBKDF2_ITERATIONS = 100_000


@dataclass
class User:
    username: str
    password_hash: str


class AuthManager:
    def __init__(self, db_path: str = os.path.join("DB", "users.db")):
        os.makedirs(os.path.dirname(db_path) or "DB", exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
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


    def hash_password(self, password: str, salt: bytes = None) -> str:
        """
        Hashes a password using PBKDF2-HMAC-SHA256 with a unique per-user salt.
        Returns: 'pbkdf2_sha256$<iterations>$<hex_salt>$<hex_hash>'.
        """
        if salt is None:
            salt = os.urandom(16)
        elif isinstance(salt, str):
            salt = bytes.fromhex(salt)

        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
        )
        return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


    def verify_password(self, password: str, stored_hash: str) -> bool:
        """
        Verifies a password against the stored salted hash using constant-time comparison.
        """
        if not stored_hash or not password:
            return False

        try:
            if stored_hash.startswith("pbkdf2_sha256$"):
                _, iterations_str, salt_hex, hash_hex = stored_hash.split("$", 3)
                iterations = int(iterations_str)
                salt = bytes.fromhex(salt_hex)
                derived = hashlib.pbkdf2_hmac(
                    "sha256",
                    password.encode("utf-8"),
                    salt,
                    iterations,
                )
                return hmac.compare_digest(derived.hex(), hash_hex)
            else:
                # Fallback for legacy unsalted SHA-256 hashes
                legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
                return hmac.compare_digest(legacy_hash, stored_hash)
        except Exception:
            return False


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

        user = self.db.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if not user:
            return False

        if not self.verify_password(password, user[0]):
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

        if token not in self.sessions or self.sessions[token] != user:
            return False

        try:
            claims = jwt.decode(
                token,
                SECRET_KEY,
                algorithms=[ALGORITHM],
                options={"require": ["exp", "username"]},
            )
        except jwt.InvalidTokenError:
            return False

        return claims["username"] == user


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



    def update_reputation(self, token: str, rep_change: int, min_rep: int = None, max_rep: int = None):
        """
        This function updates the reputation of a user connected to the given token, by rep_change points.
        Optionally clamps the reputation score within [min_rep, max_rep].
        """
        if token not in self.sessions:
            return False
        username = self.sessions[token]
        return self.update_reputation_by_username(username, rep_change, min_rep, max_rep)

    def get_reputation_by_username(self, username: str) -> int:
        """
        Returns reputation for a given username directly.
        """
        if not username:
            return -200
        row = self.db.execute("SELECT reputation FROM users WHERE username = ?", (username,)).fetchone()
        return row[0] if row else -200

    def update_reputation_by_username(self, username: str, rep_change: int, min_rep: int = None, max_rep: int = None):
        """
        Updates reputation of a user directly by username, optionally clamped within [min_rep, max_rep].
        """
        if not username:
            return False
        if min_rep is not None and max_rep is not None:
            self.db.execute(
                "UPDATE users SET reputation = MAX(?, MIN(?, reputation + ?)) WHERE username = ?",
                (min_rep, max_rep, rep_change, username)
            )
        else:
            self.db.execute(
                "UPDATE users SET reputation = reputation + ? WHERE username = ?",
                (rep_change, username)
            )
        self.db.commit()
        return True
