import json
import sqlite3
import threading
import queue
from datetime import datetime, timezone
from websockets.sync.client import connect


class ChatClient:
    def __init__(self, host="127.0.0.1", port=9000, username=None, password="123", history_db=None):
        if not username:
            raise ValueError("A username is required to connect.")

        if host.startswith("ws://") or host.startswith("wss://"):
            self.uri = host
        else:
            self.uri = f"ws://{host}:{port}"

        self.username = username
        self.token = None
        self.current_target = None

        # Non-chat responses (login, heartbeat, ...) land here for whoever asked for them.
        self._control_queue = queue.Queue()

        # Called as handler(chat_id, sender, message) for every incoming chat message.
        self._message_handler = None

        # Local history DB: one file per user by default, so two accounts on the
        # same machine don't share a history file.
        self.history_db = sqlite3.connect(
            history_db or f"chat_history_{username}.db",
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

        # Connect to WebSocket server
        self.socket = connect(self.uri)

        # Authenticate with server to get a valid token (before the listener
        # thread starts, so this reply doesn't get stolen by it).
        self._authenticate(username, password)

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

    def set_message_handler(self, handler):
        """Registers a callback invoked live for every incoming chat message."""
        self._message_handler = handler

    def _authenticate(self, username, password):
        """Logs in or signs up with the server to get an auth token."""
        login_req = {
            "action": "login",
            "payload": {
                "username": username,
                "password": password
            }
        }
        self._send(login_req)
        response = self._raw_recv()
        if response and response.get("token"):
            self.token = response["token"]

    def start_chat(self, username):
        """Sets the active chat target."""
        self.current_target = username
        return {"status": "ok", "chatting_with": username}

    def send_message(self, chat_id, message):
        """
        Sends message in the internal message format:
        sender: User UID
        address: Target UID (chat_id: user or group)
        message: Content
        """
        target_address = chat_id if chat_id else self.current_target

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
        self._save_history(target_address, self.username, "sent", message)

    def heartbeat(self):
        """Sends a heartbeat ping to verify server liveness."""
        self._send({"action": "heartbeat"})
        try:
            return self._control_queue.get(timeout=5)
        except queue.Empty:
            return None

    def get_history(self, chat_id=None, limit=50):
        """Returns the most recent stored messages, optionally filtered by chat_id."""
        if chat_id:
            rows = self.history_db.execute(
                "SELECT chat_id, sender, direction, message, timestamp FROM messages "
                "WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, limit)
            ).fetchall()
        else:
            rows = self.history_db.execute(
                "SELECT chat_id, sender, direction, message, timestamp FROM messages "
                "ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()

        return list(reversed(rows))

    def _listen_loop(self):
        """Runs in the background for the client's whole lifetime, reading every incoming message."""
        while True:
            data = self._raw_recv()
            if data is None:
                break

            action = data.get("action")

            if action == "receive":
                payload = data.get("payload", {})
                sender = payload.get("sender")
                address = payload.get("address")
                message = payload.get("message")

                # From our point of view, the "room" is the other side of a
                # direct chat, or the group address itself for a group chat.
                chat_id = sender if address == self.username else address

                self._save_history(chat_id, sender, "received", message)
                if self._message_handler:
                    self._message_handler(chat_id, sender, message)
            else:
                self._control_queue.put(data)

    def _save_history(self, chat_id, sender, direction, message):
        self.history_db.execute(
            "INSERT INTO messages (chat_id, sender, direction, message, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, sender, direction, message, datetime.now(timezone.utc).isoformat())
        )
        self.history_db.commit()

    def _raw_recv(self):
        """Reads and parses a single message straight off the socket."""
        try:
            data = self.socket.recv()
            if not data:
                return None
            return json.loads(data)
        except Exception:
            return None

    def _send(self, data):
        """Sends JSON packet over WebSocket."""
        message = json.dumps(data)
        self.socket.send(message)

    def close(self):
        """Closes the connection."""
        self.socket.close()
        self.history_db.close()
