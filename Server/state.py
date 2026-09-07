"""
This module holds state variables for the server, including the CLIENTS dictionary and ROOMS dictionary.
CLIENTS dictionary maps user UIDs to their corresponding websocket connections, allowing the server to send messages to specific users.
ROOMS dictionary maps room IDs to lists of user UIDs, allowing the server to send messages to all users in a specific room.
The module allows us to lock the state variables to prevent race conditions.
"""

import asyncio
from auth import AuthManager


auth = AuthManager()

#TODO - move to a config file
WINDOW_SECONDS = 30 # Time window in seconds for rate limiting
MAX_MESSAGES = 10
SPAM_HIT = -5

# Connected users: username -> (websocket, list of rooms, deque of message timestamps)
CLIENTS = {} 
CLIENTS_LOCK = asyncio.Lock()

# Rooms: room_id -> list of usernames
ROOMS = {}
ROOMS_LOCK = asyncio.Lock()  