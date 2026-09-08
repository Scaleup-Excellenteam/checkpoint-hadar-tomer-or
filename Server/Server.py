import os
import ssl
import sys
import json
import time
import asyncio
import logging
import websockets

# Ensure project root is in sys.path for cross-module imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from logger import setup_logger
from collections import deque
import Server.state as state
import Server.messaging as messaging
import Server.reputation as reputation

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
        user_socket, user_rooms, *user_rest = state.CLIENTS[uid]
        if room_id not in user_rooms:
            user_rooms.append(room_id)

    await websocket.send(json.dumps({"action": "room_response", "payload": {"status": "success"}}))

async def handle_login(websocket, data, client_ip, reputation_score):
    """
    This function is called from the handler, and handles the login process.
    receives the login request from the handler, validates the user and logs them in.
    if the user is logging in from a new ip, the reputation will be updated.

    websocket - senders websocket object.
    data - message data.
    client_ip - client ip address.
    reputation_score - client ip reputation score.
    """
    payload = data.get("payload") or {}
    token = None
    username = None
    try:
        username = payload.get("username").strip()
        password = payload.get("password")
        token = state.auth.login(username, password)
    except (AttributeError, TypeError):
        pass

    if token:
        # DLP/Anti-Bot: a user who was already driven to minimum reputation
        # (e.g. repeated DLP violations) stays locked out on future logins,
        # not just disconnected once.
        existing_rep = state.auth.get_reputation_by_username(username)
        if existing_rep <= state.MIN_REPUTATION:
            logger.warning(f"Rejected login for banned user '{username}' (reputation={existing_rep})")
            state.auth.logout(token)
            await websocket.send(json.dumps({"error": "Account banned due to repeated policy violations"}))
            return

        state.CLIENTS[username] = (websocket, [], deque(), time.monotonic())
        logger.info(f"User '{username}' logged in successfully")
        await websocket.send(json.dumps({"action": "login_response", "token": token}))
        if reputation_score < -5:
            # if reputation is bad but not under block threshold, user starts with lower rep score
            state.auth.update_reputation(token, state.SUSPICIOUS_IP_HIT, state.MIN_REPUTATION, state.MAX_REPUTATION)
            logger.info(f"User '{username}' connected from low reputation ip:{client_ip}")
    else:
        logger.warning(f"Login failed for user '{username}'")
        await websocket.send(json.dumps({"error": "Login failed"}))


async def handle_signup(websocket, data):
    """
    This function is called from the handler, and handles the signup process.
    receives the signup request from the handler, validates the user and signs them up.

    websocket - senders websocket object.
    data - message data.
    """
    payload = data.get("payload") or {}
    success = False
    username = None
    try:
        username = payload.get("username").strip()
        password = payload.get("password")
        success = state.auth.signup(username, password)
    except (AttributeError, TypeError):
        pass
    if not success:
        logger.warning(f"Signup failed: username '{username}' is already taken")
        await websocket.send(json.dumps({"error": "Username already taken"}))
    else:
        token = state.auth.login(username, password)
        logger.info(f"User '{username}' signed up successfully")
        await websocket.send(json.dumps({"action": "signup_response", "token": token}))


async def handle_logout(websocket, data):
    """
    This function is called from the handler, and handles the logout process.
    receives the logout request from the handler, validates the user and logs them out.

    websocket - senders websocket object.
    data - message data.
    """
    token = data.get("token")
    if token:
        state.auth.logout(token)
    await websocket.send(json.dumps({"action": "logout_response", "status": "success"}))
    await websocket.close()


async def handle_heartbeat(websocket):
    """
    This function handles the heartbeat. It is kept for testing and compatibility.
    """
    logger.info(f"Heartbeat message received {websocket}")
    await websocket.send(json.dumps({"action": "heartbeat"}))


async def reputation_regrow_loop(interval_seconds=1):
    """
    Background task that periodically regrows reputation for connected users
    who have maintained clean activity for at least REGROW_WINDOW_SECONDS.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        now = time.monotonic()
        for user, client_data in list(state.CLIENTS.items()):
            if len(client_data) > 3:
                ws, rooms, msg_deque, last_clean = client_data
                if now - last_clean >= state.REGROW_WINDOW_SECONDS:
                    current_rep = state.auth.get_reputation_by_username(user)
                    if current_rep < state.MAX_REPUTATION:
                        state.auth.update_reputation_by_username(
                            user, state.REGROW_STEP, state.MIN_REPUTATION, state.MAX_REPUTATION
                        )
                        new_rep = state.auth.get_reputation_by_username(user)
                        logger.info(f"[REPUTATION_REGROW] User '{user}' regrew by +{state.REGROW_STEP} to {new_rep}")
                    state.CLIENTS[user] = (ws, rooms, msg_deque, now)

async def handler(websocket):
    """
    Main WebSocket connection handler.
    Dispatches incoming messages to the corresponding modular handlers.
    """
    client_ip = websocket.remote_address[0]

    #run an ip check on client
    reputation_score, rep_stats = await reputation.check_ip_rep(client_ip)
    #TODO - tune threshold according to api
    logger.info(f"IP: {client_ip} | Reputation score: {reputation_score} | Stats: {rep_stats}")
    if reputation_score < state.REPUTATION_THRESHOLD:
        #if reputation under threshold, deny connection and close
        logger.warning(f"Reputation threshold exceeded: {state.REPUTATION_THRESHOLD}, closing connection with: {client_ip}")
        await websocket.send(json.dumps({"error": "Connection closed due to low reputation score"}))
        await websocket.close()
        return

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
                await handle_heartbeat(websocket)

            elif action == "join_room":
                await manage_room(websocket, data.get("room_id"), data.get("uid"))

            elif action == "login":
                await handle_login(websocket, data, client_ip, reputation_score)

            elif action == "signup":
                await handle_signup(websocket, data)

            elif action == "logout":
                await handle_logout(websocket, data)
                break

            elif action == "manage_room":
                payload = data.get("payload", {})
                room_id = payload.get("room_id")
                uid = payload.get("username") or payload.get("uid")
                await manage_room(websocket, room_id, uid)

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
        for user, (w_sockets, user_rooms, *user_rest) in list(state.CLIENTS.items()):
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
                    state.CLIENTS[username] = (websocket,[],deque(),time.monotonic())
                    logger.info(f"User '{username}' logged in successfully")


    except websockets.ConnectionClosed:
        logger.info("Client connection closed")
    except Exception as e:
        logger.error(f"Unexpected error in handler: {e}", exc_info=True)
    finally:
        pass # TODO check if anything is needed here



async def main():
    logger.info("Starting Chat Server...")

    # Background task for idle reputation regrowth
    asyncio.create_task(reputation_regrow_loop())

    async with websockets.serve(handler, "0.0.0.0", 9000, ssl=ssl_context):
        logger.info("Server running on ws://0.0.0.0:9000")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
