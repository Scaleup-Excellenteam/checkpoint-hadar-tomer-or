import socket
import json
import sqlite3
import threading
import queue
from datetime import datetime, timezone


class ChatClient:
    def __init__(self, host="127.0.0.1", port=5000, history_db="chat_history.db"):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))

        self.reader = self.socket.makefile("r", encoding="utf-8")

        self.history_db = sqlite3.connect(history_db, check_same_thread=False)
        self.history_db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                direction TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        self.history_db.commit()

        # Non-chat responses (e.g. the start_chat ack) land here for whoever asked for them.
        self._control_queue = queue.Queue()

        # Called as handler(chat_id, message) for every incoming chat message.
        self._message_handler = None

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()


    def set_message_handler(self, handler):
        """Registers a callback invoked live for every incoming chat message."""
        self._message_handler = handler


    def _listen_loop(self):
        """Runs in the background for the client's whole lifetime, reading every incoming line."""
        while True:
            line = self.reader.readline()
            if not line:
                break

            parsed = json.loads(line)
            message = parsed.get("message")

            if message is not None:
                chat_id = parsed.get("chat_id") or parsed.get("from")
                self._save_history(chat_id, "received", message)
                if self._message_handler:
                    self._message_handler(chat_id, message)
            else:
                self._control_queue.put(parsed)


    def start_chat(self, username):
        request = {
            "type": "start_chat",
            "target": username
        }

        self._send(request)

        return self._control_queue.get(timeout=5)


    def send_message(self, chat_id, message):
        request = {
            "type": "message",
            "chat_id": chat_id,
            "message": message
        }

        self._send(request)
        self._save_history(chat_id, "sent", message)


    def _save_history(self, chat_id, direction, message):
        self.history_db.execute(
            "INSERT INTO messages (chat_id, direction, message, timestamp) VALUES (?, ?, ?, ?)",
            (chat_id, direction, message, datetime.now(timezone.utc).isoformat())
        )
        self.history_db.commit()


    def get_history(self, chat_id=None, limit=50):
        """Returns the most recent stored messages, optionally filtered by chat_id."""
        if chat_id:
            rows = self.history_db.execute(
                "SELECT chat_id, direction, message, timestamp FROM messages "
                "WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, limit)
            ).fetchall()
        else:
            rows = self.history_db.execute(
                "SELECT chat_id, direction, message, timestamp FROM messages "
                "ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()

        return list(reversed(rows))


    def _send(self, data):
        message = json.dumps(data) + "\n"
        self.socket.sendall(message.encode("utf-8"))


    def close(self):
        self.socket.close()
        self.history_db.close()
        