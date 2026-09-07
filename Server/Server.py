import os
import ssl
import sys
import json
import asyncio
import logging
import websockets
# Ensure project root is in sys.path for cross-module imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from logger import setup_logger
import Server.state as state
import Server.messaging as messaging

# create ssl context for secure connection
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")

# Initialize logger
setup_logger("SERVER")
logger = logging.getLogger(__name__)



async def manage_room(websocket, room_id, uid):
    """
    Receive request from user.
    validate uid and socket against active user list
    check if room exists - if yes, add user to room.
    if not, create room and add user to room.

    websocket - senders websocket object.
    room_id - room ID, the room is a special user standing in for multiple users.
    uid - user ID of the one making the request.
    """
    if uid not in state.CLIENTS or state.CLIENTS[uid][0] != websocket:
        logger.error("rejected request with wrong uid or websocket")
        return

    if room_id not in state.ROOMS:
        state.ROOMS[room_id] = []
        logger.info(f"Created new room: {room_id}")

    if uid not in state.ROOMS[room_id]:
        state.ROOMS[room_id].append(uid)
        logger.info(f"Added user '{uid}' to room '{room_id}'")

    if uid in state.CLIENTS:
        user_socket, user_rooms = state.CLIENTS[uid]
        if room_id not in user_rooms:
            user_rooms.append(room_id)

    await websocket.send(json.dumps({"action": "room_response", "payload": {"status": "success"}}))


async def handler(websocket):
    """
    Main WebSocket connection handler.
    Dispatches incoming messages to the corresponding modular handlers.
    """
    try:
        async for raw_message in websocket:
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.error("Received invalid JSON from client")
                await websocket.send(json.dumps({"error": "Invalid JSON format"}))
                continue

            action = data.get("action")
            logger.info(f"Handling action: {action}")

            if action == "send":
                await messaging.receive(websocket, data)

            elif action == "heartbeat":
                # kept for compatibility, but websockets library handles heartbeats automatically.
                logger.info(f"Heartbeat message received {websocket}")
                await websocket.send(json.dumps({"action": "heartbeat"}))

            elif action == "join_room":
                await manage_room(websocket, data["room_id"], data["uid"])

            elif action == "login":
                payload = data.get("payload", {})
                username = payload.get("username")
                password = payload.get("password", "123")

                token = state.auth.login(username, password)

                if token:
                    state.CLIENTS[username] = (websocket,[])
                    logger.info(f"User '{username}' logged in successfully")
                    await websocket.send(json.dumps({"action": "login_response", "token": token}))
                else:
                    logger.warning(f"Login failed for user '{username}'")
                    await websocket.send(json.dumps({"error": "Login failed"}))

            elif action == "signup":
                payload = data.get("payload", {})
                username = payload.get("username")
                password = payload.get("password", "123")
                success = state.auth.signup(username, password)
                print(username," ", password)
                if not success:
                    logger.warning(f"Signup failed: username '{username}' is already taken")
                    await websocket.send(json.dumps({"error": "Username already taken"}))
                else:
                    token = state.auth.login(username, password)
                    state.CLIENTS[username] = (websocket, [])
                    logger.info(f"User '{username}' signed up successfully")
                    await websocket.send(json.dumps({"action": "signup_response", "token": token}))

            elif action == "logout":
                token = data.get("token")
                if token:
                    state.auth.logout(token)
                await websocket.send(json.dumps({"action": "logout_response", "status": "success"}))
                await websocket.close()
                break

            elif action == "manage_room":
                payload = data.get("payload", {})
                room_id = payload.get("room_id")
                uid = payload.get("username") or payload.get("uid")
                token = data.get("token")
                await manage_room(websocket, room_id, uid, token)

            else:
                logger.warning(f"Received unknown action: {action}")
                await websocket.send(json.dumps({"error": f"Unknown action: {action}"}))

    except websockets.ConnectionClosed:
        logger.info("Client connection closed")
    except Exception as e:
        logger.error(f"Unexpected error in handler: {e}", exc_info=True)
    finally:
        # Remove disconnected socket from CLIENTS
        disconnected_users = []
        for user, (w_sockets,user_rooms) in list(state.CLIENTS.items()):
            if w_sockets == websocket:
                for room_id in user_rooms:
                    #lock rooms and remove user
                    async with state.ROOMS_LOCK:
                        if room_id in state.ROOMS and user in state.ROOMS[room_id]:
                            state.ROOMS[room_id].remove(user)
                            logger.info(f"Removed user '{user}' from room '{room_id}'")
                disconnected_users.append(user)
                del state.CLIENTS[user]

        if disconnected_users:
            logger.info(f"Removed disconnected user session(s): {disconnected_users}")

async def account_handler(websocket, path):
    try:
        async for raw_message in websocket:
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.error("Received invalid JSON from client")
                await websocket.send(json.dumps({"error": "Invalid JSON format"}))
                continue

            action = data.get("action")
            logger.info(f"Handling action: {action}")
            if action == "login":
                payload = data.get("payload", {})
                username = payload.get("username")
                password = payload.get("password")
                if state.auth.login(username, password):
                    state.CLIENTS[username] = (websocket,[])
                    logger.info(f"User '{username}' logged in successfully")


    except websockets.ConnectionClosed:
        logger.info("Client connection closed")
    except Exception as e:
        logger.error(f"Unexpected error in handler: {e}", exc_info=True)
    finally:
        pass # TODO check if anything is needed here



async def main():
    logger.info("Starting Chat Server...")



    async with websockets.serve(handler, "0.0.0.0", 9000, ssl=ssl_context):
        logger.info("Server running on ws://0.0.0.0:9000")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
