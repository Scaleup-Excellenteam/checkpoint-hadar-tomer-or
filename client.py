import socket
import json


class ChatClient:
    def __init__(self, host="127.0.0.1", port=5000):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))

        self.reader = self.socket.makefile("r", encoding="utf-8")


    def start_chat(self, username):
        request = {
            "type": "start_chat",
            "target": username
        }

        self._send(request)

        response = self.receive_message()

        return response


    def send_message(self, chat_id, message):
        request = {
            "type": "message",
            "chat_id": chat_id,
            "message": message
        }

        self._send(request)


    def receive_message(self):
        data = self.reader.readline()

        if not data:
            return None

        return json.loads(data)


    def _send(self, data):
        message = json.dumps(data) + "\n"
        self.socket.sendall(message.encode("utf-8"))


    def close(self):
        self.socket.close()
        