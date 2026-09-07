"""
This module handles messaging between the client and the server.
"""
import json
import time
import asyncio
import Server.state as state
import logging
from auth import AuthManager
from collections import deque
logger = logging.getLogger(__name__)




async def send(address, payload):
    """
    send message to address contained in payload.
    checks if client is in CLIENTS (active websocket connection).
    address - Address UID of the message.
    payload - Payload of the message.
    returns True if message was succesfuly delivered, False if failed to send.
    """
    client_entry = state.CLIENTS.get(address) # verify address is valid client
    if not client_entry:
        logger.error(f"Client {address} not found")
        return False
    recipient_ws = client_entry[0]  # Extract websocket from tuple
    if not recipient_ws:
        logger.error(f"Address {address} not found in CLIENTS")
        return False

   
    logger.info(f"Sending message to: {address}")
    # try sending message, handle exceptions if raised. TODO - add retry for failed sends, 1-2 retries.
    try:
        await recipient_ws.send(json.dumps({
            "action": "receive",
            "payload": payload
        }))
    except Exception as e:
        logger.error(f"Failed to send message to {address}: {e}")
        return False

    return True



async def room_send(address, payload):
    """
    TODO - verify async works
    Send message to room address contained in payload.
    room address is a type of user that holds a list of user UIDs.
    the function iterates through the list of user UIDs and sends the message to each user.

    address - Address UID of the message.
    payload - Payload of the message.
    returns True if message was succesfuly delivered to all users, False if any user failed to receive the message.
    """
    sender = payload.get("sender")
    recipients = [user for user in state.ROOMS.get(address, []) if user != sender]  # Exclude the sender from recipients
    if not recipients:
        logger.error(f"No recipients found for room: {address}")
        return False

    tasks = [send(user, payload) for user in recipients]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    send_failures = []
    for user, result in zip(recipients, results):
        if isinstance(result, Exception) or result is False:
            logger.error(f"Failed to send message to {user}: {result}")
            send_failures.append(user)
        else:
            logger.info(f"Successfully sent message to {user}")
            pass
    #TODO - add retry for failed sends, 1-2 retries.
    if send_failures:
        logger.error(f"Failed to send message to the following users: {send_failures}")
        return False

    return True


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
        existing_rooms = state.CLIENTS[sender][1] if sender in state.CLIENTS else []
        existing_deque = state.CLIENTS[sender][2] if sender in state.CLIENTS else deque()
        existing_clean = state.CLIENTS[sender][3] if (sender in state.CLIENTS and len(state.CLIENTS[sender]) > 3) else time.monotonic()
        state.CLIENTS[sender] = (websocket, existing_rooms, existing_deque, existing_clean)

    # verify sender with auth TODO - this should be done early in a login, then maintain a TLS connection.
    if not ( state.auth.validate_user_token(sender, token) or state.auth.validate_user_token(sender, address) ): #
        await websocket.send(json.dumps({"error": "Auth failed"}))
        return

    now = time.monotonic()
    user_deque = state.CLIENTS[sender][2] #if sender in state.CLIENTS else [] TODO check if section is needed
    while user_deque and (now - user_deque[0] > state.WINDOW_SECONDS):
        user_deque.popleft() # remove old messages
    if len(user_deque) >= state.MAX_MESSAGES:
        logger.warning(f"Rate limit exceeded for user: {sender}")
        await websocket.send(json.dumps({"error": "Rate limit exceeded"}))
        state.auth.update_reputation(token, state.SPAM_HIT, state.MIN_REPUTATION, state.MAX_REPUTATION)  # Decrease reputation for rate limit violation
        # Reset clean activity cooldown timer
        if sender in state.CLIENTS:
            c_ws, c_rooms, c_deq, _ = state.CLIENTS[sender]
            state.CLIENTS[sender] = (c_ws, c_rooms, c_deq, now)
        return
    user_deque.append(now)  # Add the current timestamp

    # Check for active reputation regrowth on compliant message
    if sender in state.CLIENTS and len(state.CLIENTS[sender]) > 3:
        c_ws, c_rooms, c_deq, last_clean = state.CLIENTS[sender]
        if now - last_clean >= state.REGROW_WINDOW_SECONDS:
            current_rep = state.auth.get_reputation(token)
            if current_rep < state.MAX_REPUTATION:
                state.auth.update_reputation(token, state.REGROW_STEP, state.MIN_REPUTATION, state.MAX_REPUTATION)
                new_rep = state.auth.get_reputation(token)
                logger.info(
                    f"[REPUTATION_REGROW] User '{sender}' reputation regrew by +{state.REGROW_STEP} to {new_rep} "
                    f"(Reason: {state.REGROW_WINDOW_SECONDS}s compliant activity)"
                )
            state.CLIENTS[sender] = (c_ws, c_rooms, c_deq, now)

    
    # forward the internal message to the send() func.
    logger.info(f"Received message from: {sender} to: {address}")
    if address in state.ROOMS:
        # address is room, forward to room_send()
        success = await room_send(address, {
            "sender": sender,
            "address": address,
            "message": message
        })
    elif address not in state.CLIENTS:
        # address does not exist
        logger.error(f"Address {address} not found")
        await websocket.send(json.dumps({"error": f"Address {address} not found"}))
        return
    else:
        # address is a single user, forward to send()
        success = await send(address, {
            "sender": sender,
            "address": address,
            "message": message
        })

    if not success:
        # the message failed to send, log the error and send an error message back to the sender.
        logger.error(f"Failed to send message from: {sender} to: {address}")
        await websocket.send(json.dumps({"error": f"Failed to send message to {address}"}))
        return False
    # log the successful send and send an ack back to the sender.
    logger.info(f"sent message from: {sender} to: {address}")
    await websocket.send(json.dumps({"action": "ack", "payload": {"status": "success"}})) # TODO - add msg id
