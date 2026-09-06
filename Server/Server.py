import sys
import os
import json
import asyncio
import websockets

# Import your auth contracts
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth import AuthManager

auth = AuthManager()

# Connected users: user_uid -> websocket
CLIENTS = {}


async def send(address, payload):
    """
    send message to address contained in payload.
    checks if client is in CLIENTS (active websocket connection).
    address - Address UID of the message.
    payload - Payload of the message.
    """
    recipient_ws = CLIENTS.get(address)
    if recipient_ws:
        await recipient_ws.send(json.dumps({
            "action": "receive",
            "payload": payload
        }))


async def receive(websocket, data):
    """
    receive message from an address contained in data.
    checks if client is in CLIENTS (active websocket connection).
    websocket - the websocket object the message is sent from.
    data - content of the message, includes the payload (massage using internal message format) and JWT token for auth.
    """
    token = data.get("token")
    payload = data.get("payload", {})
    sender = payload.get("sender")
    address = payload.get("address")
    message = payload.get("message")

    # register the sender's websocket connection
    if sender:
        CLIENTS[sender] = websocket

    # verify sender with auth
    if not ( auth.validate_user_token(sender, token) and auth.validate_user_address(sender, address) ):
        await websocket.send(json.dumps({"error": "Auth failed"}))
        return

    # forward the internal message to the send() func.
    await send(address, {
        "sender": sender,
        "address": address,
        "message": message
    })


async def heartbeat(websocket):
    """
    heartbeat message is sent from websocket to address contained in payload.
    """
    await websocket.send(json.dumps({"action": "heartbeat"}))


async def handler(websocket):
    """
    async handler.
    """
    try:
        async for raw_message in websocket:
            data = json.loads(raw_message)
            action = data.get("action")

            if action == "send":
                await receive(websocket, data)

            elif action == "heartbeat":
                await heartbeat(websocket)

            elif action == "login":
                payload = data.get("payload", {})
                username = payload.get("username")
                password = payload.get("password", "123")
                token = auth.login(username, password)
                if not token:
                    auth.signup(username, password)
                    token = auth.login(username, password)
                CLIENTS[username] = websocket
                await websocket.send(json.dumps({"action": "login_response", "token": token}))

    except websockets.ConnectionClosed:
        pass
    finally:
        # Remove disconnected socket
        for user, ws in list(CLIENTS.items()):
            if ws == websocket:
                del CLIENTS[user]


async def main():
    async with websockets.serve(handler, "0.0.0.0", 9000):
        print("Server running on ws://0.0.0.0:9000")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
