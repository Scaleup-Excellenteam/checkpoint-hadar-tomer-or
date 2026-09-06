import json
from websockets.sync.client import connect


class ChatClient:
    def __init__(self, host="127.0.0.1", port=9000, username=None, password="123"):
        if not username:
            raise ValueError("A username is required to connect.")

        if host.startswith("ws://") or host.startswith("wss://"):
            self.uri = host
        else:
            self.uri = f"ws://{host}:{port}"

        self.username = username
        self.token = None
        self.current_target = None

        # Connect to WebSocket server
        self.socket = connect(self.uri)

        # Authenticate with server to get a valid token
        self._authenticate(username, password)

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
        response = self.receive_message()
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

    def receive_message(self):
        """Receives a message from the WebSocket."""
        try:
            data = self.socket.recv()
            if not data:
                return None
            return json.loads(data)
        except Exception:
            return None

    def heartbeat(self):
        """Sends a heartbeat ping to verify server liveness."""
        self._send({"action": "heartbeat"})
        return self.receive_message()

    def _send(self, data):
        """Sends JSON packet over WebSocket."""
        message = json.dumps(data)
        self.socket.send(message)

    def close(self):
        """Closes the connection."""
        self.socket.close()