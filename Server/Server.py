import os
import sys
import json
import asyncio
import logging
import websockets




# Import your auth contracts
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth import AuthManager

auth = AuthManager()

# Connected users: user_uid -> websocket
CLIENTS = {}
GROUPS = []

async def send(address, payload):
    """
    send message to address contained in payload.
    checks if client is in CLIENTS (active websocket connection).
    address - Address UID of the message.
    payload - Payload of the message.
    """
    recipient_ws = CLIENTS.get(address) # verify address is valid client
    if recipient_ws:
        await recipient_ws.send(json.dumps({
            "action": "receive",
            "payload": payload
        }))


async def receive(websocket, data):
    """
    Receive message from an address contained in data.
    checks if client is in CLIENTS (active websocket connection).
    websocket - the websocket object the message is sent from.
    data - content of the message, includes the payload (massage using internal message format) and JWT token for auth.
    TODO - add ACK
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
    if not ( auth.validate_user_token(sender, token) or auth.validate_user_token(sender, address) ): #
        await websocket.send(json.dumps({"error": "Auth failed"}))
        return

    # forward the internal message to the send() func.
    print(f"Received message from: {sender} to: {address}")
    await send(address, {
        "sender": sender,
        "address": address,
        "message": message
    })
    #logger.info(f"Return ack")
    await websocket.send(json.dumps({"action": "ack", "payload": {"status": "success"}})) # TODO - add msg id


async def heartbeat(websocket):
    """
    Heartbeat message is sent from websocket to address contained in payload.
    websocket - the websocket object the message is sent from.
    """
    logger.info(f"Heartbeat message received {websocket}")
    asyncio.create_task(websocket.send(json.dumps({"action": "heartbeat"})))

async def group_send(address, payload):
    """
    TODO - verify async works
    Send message to group address contained in payload.
    group address is a type of user that holds a list of user UIDs.
    the function iterates through the list of user UIDs and sends the message to each user.

    address - Address UID of the message.
    payload - Payload of the message.
    """
    for user in GROUPS[address]:
        # creates an async task group to send messages to each group member
        async with asyncio.TaskGroup() as group_addresses:
            group_addresses.create_task(send(user, payload))
        await group_addresses.join() # awaits


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


async def manage_room(room_id, uid):
    """
    Receive request from user.
    validate uid.
    check if room exists - if yes, add user to room.
    if not, create room and add user to room.

    room_id - room ID, the room is a special user standing in for multiple users.
    uid - user ID of the one making the request.
    """
    if not auth.validate_user_token(uid):
        await websocket.send(json.dumps({"error": "Auth failed"}))
    if room_id not in GROUPS:
        # create room if
        GROUPS[room_id] = []
    GROUPS[room_id].append(uid)
    await websocket.send(json.dumps({"action": "room_response", "payload": {"status": "success"}})) #return ack

async def main():
    #logging.basicConfig(filename="server.log", format='%(asctime)s %(levelname)s: %(message)s', level=logging.DEBUG) TODO - change logging method
    async with websockets.serve(handler, "0.0.0.0", 9000):
        print("Server running on ws://0.0.0.0:9000")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
