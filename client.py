import json
import sqlite3
import threading
import queue
from datetime import datetime, timezone
from websockets.sync.client import connect


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

        # Start listening for incoming messages
        self._listener_thread = threading.Thread(
            target=self._listen_loop,
            daemon=True
        )
        self._listener_thread.start()

    def signup(self, username, password):
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
            return False

        if response.get("action") == "signup_response":
            return True

        return False


    def login(self, username, password):
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
            return False

        token = response.get("token")

        if not token:
            return False

        self.username = username
        self.token = token

        self._open_history_db()

        return True


    def logout(self):

        if not self.token:
            return False

        request = {
            "action": "logout",
            "token": self.token
        }

        self._send(request)

        try:
            response = self._control_queue.get(timeout=5)
        except queue.Empty:
            return False

        if response.get("action") != "logout_response":
            return False

        self.token = None
        self.username = None
        self.current_target = None

        if self.history_db:
            self.history_db.close()
            self.history_db = None

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

        return True

    def heartbeat(self):

        self._send({
            "action": "heartbeat"
        })

        try:
            return self._control_queue.get(timeout=5)

        except queue.Empty:
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

                if self._message_handler:
                    self._message_handler(
                        chat_id,
                        sender,
                        message
                    )

            # Login / signup / logout / heartbeat responses
            else:
                self._control_queue.put(data)

    def _raw_recv(self):

        try:
            data = self.socket.recv()

            if not data:
                return None

            return json.loads(data)

        except Exception:
            return None

    def _send(self, data):

        message = json.dumps(data)

        self.socket.send(message)

    def close(self):

        self.socket.close()

        if self.history_db:
            self.history_db.close()
            self.history_db = None