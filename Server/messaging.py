"""
This module handles messaging between the client and the server.
"""
import json
import asyncio
import Server.state as state
import logger as logger
from auth import AuthManager


auth = AuthManager()


async def send(address, payload):
    """
    send message to address contained in payload.
    checks if client is in CLIENTS (active websocket connection).
    address - Address UID of the message.
    payload - Payload of the message.
    returns True if message was succesfuly delivered, False if failed to send.
    """
    recipient_ws = state.CLIENTS.get(address) # verify address is valid client
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
        state.CLIENTS[sender] = websocket

    # verify sender with auth TODO - this should be done early in a login, then maintain a TLS connection.
    if not ( auth.validate_user_token(sender, token) or auth.validate_user_token(sender, address) ): #
        await websocket.send(json.dumps({"error": "Auth failed"}))
        return

    
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
