import json
import sqlite3
import threading
import queue
import logging
from datetime import datetime, timezone
from websockets.sync.client import connect

from logger import setup_logger

setup_logger("CLIENT")
logger = logging.getLogger(__name__)


class ChatClient:
    def __init__(self, host="127.0.0.1", port=9000, history_db=None):
        ssl_context = ssl.create_default_context(cafile="cert.pem")
        ssl_context.check_hostname = False
        if host.startswith("ws://") or host.startswith("wss://"):
            self.uri = host
        else:
            self.uri = f"wss://{host}:{port}"

        self.username = None
        self.token = None
        self.current_target = None

        self.history_db_path = history_db
        self.history_db = None

        # Responses such as login/signup/heartbeat
        self._control_queue = queue.Queue()

        # Callback for incoming chat messages
        self._message_handler = None

        # Connect to server
        self.socket = connect(self.uri)
        logger.info("Connected to server at %s", self.uri)

        # Start listening for incoming messages
        self._listener_thread = threading.Thread(
            target=self._listen_loop,
            daemon=True
        )
        self._listener_thread.start()
        logger.debug("Listener thread started")

    def signup(self, username, password):
        logger.debug("Signing up user '%s'", username)

        request = {
            "action": "signup",
            "payload": {
                "username": username,
                "password": password
            }
        }

        self._send(request)

        try:
            response = self._control_queue.get(timeout=5)
        except queue.Empty:
            logger.warning("Signup timed out for user '%s'", username)
            return False

        if response.get("action") == "signup_response":
            logger.info("Signup successful for user '%s'", username)
            return True

        logger.warning("Signup failed for user '%s': %s", username, response)
        return False


    def login(self, username, password):
        logger.debug("Logging in user '%s'", username)

        request = {
            "action": "login",
            "payload": {
                "username": username,
                "password": password
            }
        }

        self._send(request)

        try:
            response = self._control_queue.get(timeout=5)
        except queue.Empty:
            logger.warning("Login timed out for user '%s'", username)
            return False

        token = response.get("token")

        if not token:
            logger.warning("Login failed for user '%s': %s", username, response)
            return False

        self.username = username
        self.token = token

        self._open_history_db()

        logger.info("User '%s' logged in successfully", username)

        return True


    def logout(self):

        if not self.token:
            return False

        username = self.username
        logger.debug("Logging out user '%s'", username)

        request = {
            "action": "logout",
            "token": self.token
        }

        self._send(request)

        try:
            response = self._control_queue.get(timeout=5)
        except queue.Empty:
            logger.warning("Logout timed out for user '%s'", username)
            return False

        if response.get("action") != "logout_response":
            logger.warning("Logout failed for user '%s': %s", username, response)
            return False

        self.token = None
        self.username = None
        self.current_target = None

        if self.history_db:
            self.history_db.close()
            self.history_db = None

        logger.info("User '%s' logged out", username)

        return True

    def set_message_handler(self, handler):
        """
        Set function that will be called when a message arrives.
        """
        self._message_handler = handler


    def start_chat(self, username):
        """
        Set current chat target.
        """
        self.current_target = username

        return {
            "status": "ok",
            "chatting_with": username
        }


    def send_message(self, chat_id, message):

        if not self.token:
            return False

        target_address = chat_id if chat_id else self.current_target

        if not target_address:
            return False

        request = {
            "action": "send",
            "token": self.token,
            "payload": {
                "sender": self.username,
                "address": target_address,
                "message": message
            }
        }

        self._send(request)

        self._save_history(
            target_address,
            self.username,
            "sent",
            message
        )

        logger.debug("Message sent to '%s': %s", target_address, message)

        return True

    def heartbeat(self):
        logger.debug("Sending heartbeat")

        self._send({
            "action": "heartbeat"
        })

        try:
            response = self._control_queue.get(timeout=5)
            logger.debug("Heartbeat response: %s", response)
            return response

        except queue.Empty:
            logger.warning("Heartbeat timed out")
            return None

    def _open_history_db(self):

        db_path = (
            self.history_db_path
            or f"chat_history_{self.username}.db"
        )

        self.history_db = sqlite3.connect(
            db_path,
            check_same_thread=False
        )

        self.history_db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                sender TEXT,
                direction TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)

        self.history_db.commit()


    def get_history(self, chat_id=None, limit=50):

        if not self.history_db:
            return []

        if chat_id:
            rows = self.history_db.execute(
                """
                SELECT chat_id, sender, direction, message, timestamp
                FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit)
            ).fetchall()

        else:
            rows = self.history_db.execute(
                """
                SELECT chat_id, sender, direction, message, timestamp
                FROM messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

        return list(reversed(rows))

    def _save_history(self, chat_id, sender, direction, message):

        if not self.history_db:
            return

        self.history_db.execute(
            """
            INSERT INTO messages
            (chat_id, sender, direction, message, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                sender,
                direction,
                message,
                datetime.now(timezone.utc).isoformat()
            )
        )

        self.history_db.commit()

    def _listen_loop(self):

        while True:

            data = self._raw_recv()

            if data is None:
                logger.debug("Listener loop exiting: connection closed")
                break

            action = data.get("action")

            # Normal chat message
            if action == "receive":

                payload = data.get("payload", {})

                sender = payload.get("sender")
                address = payload.get("address")
                message = payload.get("message")

                if address == self.username:
                    chat_id = sender
                else:
                    chat_id = address

                self._save_history(
                    chat_id,
                    sender,
                    "received",
                    message
                )

                logger.info("Message received from '%s' in '%s'", sender, chat_id)

                if self._message_handler:
                    self._message_handler(
                        chat_id,
                        sender,
                        message
                    )

            # Login / signup / logout / heartbeat responses
            else:
                logger.debug("Control response received: %s", data)
                self._control_queue.put(data)

    def _raw_recv(self):

        try:
            data = self.socket.recv()

            if not data:
                return None

            return json.loads(data)

        except Exception:
            logger.debug("Failed to receive/parse message", exc_info=True)
            return None

    def _send(self, data):

        message = json.dumps(data)

        self.socket.send(message)

    def close(self):
        logger.info("Closing connection for user '%s'", self.username)

        self.socket.close()

        if self.history_db:
            self.history_db.close()
            self.history_db = None