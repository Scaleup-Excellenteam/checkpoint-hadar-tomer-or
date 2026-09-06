"""
This module handles heartbeat messages from the client, using them to keep track of active websocket connections. 
It also handles the removal of inactive clients from the CLIENTS dictionary.
"""

import json
import asyncio
import Server.state as state
import logger as logger


async def heartbeat(username, websocket):
    """
    TODO - check if websockets handles heartbeat messages automatically, if so remove this function.

    Heartbeat message is sent from websocket to address contained in payload.
    locks the CLIENTS dictionary to update the last heartbeat time for the websocket.
    websocket - the websocket object the message is sent from.
    """
    logger.info(f"Heartbeat message received {websocket}")
    asyncio.create_task(websocket.send(json.dumps({"action": "heartbeat"})))
    async with state.CLIENTS_LOCK:
        #update last heartbeat for socket.
        state.CLIENTS[username] = { "websocket": websocket, "last_heartbeat": asyncio.get_event_loop().time()}  
    
async def remove_inactive_clients():
    """
    Checks for inactive clients on a set interval, and removes them from the CLIENTS dictionary.
    A client is considered inactive if it hasn't sent a heartbeat message within the last 30 seconds.
    """
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds TODO - maybe offload scheduling to a separate module/centralized scheduler.
        current_time = asyncio.get_event_loop().time()
        async with state.CLIENTS_LOCK:
            inactive_clients = [w_socket for w_socket, client_info 
                                in state.CLIENTS.items() 
                                if current_time - client_info.get("last_heartbeat", 0) > 30]
            for inactive_socket in inactive_clients:
                del state.CLIENTS[inactive_socket]
                logger.info(f"Removed inactive client: {inactive_socket}")