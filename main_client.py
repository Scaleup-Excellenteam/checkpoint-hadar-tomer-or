import logging

from logger import setup_logger

# Set up before importing ChatClient, so this process's log file/role
# ("MAIN_CLIENT") wins over client.py's own setup_logger("CLIENT") call.
setup_logger("MAIN_CLIENT")
logger = logging.getLogger(__name__)

from client import ChatClient

server_ip = input("Server IP [press Enter for 127.0.0.1]: ").strip() or "127.0.0.1"

logger.info("Connecting to server at %s", server_ip)
client = ChatClient(host=server_ip, port=9000)

current_room = None


def on_message(chat_id, sender, message):
    # Only interrupt the screen with messages for the room we're currently in.
    if chat_id == current_room:
        print(f"\n{sender}: {message}")


client.set_message_handler(on_message)


def enter_room(room):
    global current_room
    current_room = room
    client.start_chat(room)
    logger.info("Entered room/chat '%s'", room)

    print(f"--- History with {room} ---")
    history = client.get_history(room)
    logger.debug("Loaded %d history rows for '%s'", len(history), room)
    for chat_id, sender, direction, message, timestamp in history:
        who = "you" if direction == "sent" else sender
        print(f"[{timestamp}] {who}: {message}")

    print(f"--- Live chat with {room} (type /leave to go back) ---")
    while True:
        text = input("> ")
        if text == "/leave":
            logger.debug("Leaving room/chat '%s'", room)
            break
        client.send_message(room, text)

    current_room = None


def auth_menu():
    """Signup/login screen. Returns True once logged in, False on exit."""
    while True:
        print("\n1. Signup")
        print("2. Login")
        print("3. Exit")

        choice = input("> ").strip()

        if choice == "1":
            username = input("Username: ").strip()
            password = input("Password: ").strip()
            logger.debug("Signup attempt for '%s'", username)
            if client.signup(username, password):
                print("Signup successful. You can now log in.")
            else:
                print("Signup failed (username may already be taken).")

        elif choice == "2":
            username = input("Username: ").strip()
            password = input("Password: ").strip()
            logger.debug("Login attempt for '%s'", username)
            if client.login(username, password):
                print(f"Logged in as {client.username}")
                return True
            else:
                print("Login failed.")

        elif choice == "3":
            logger.info("User exited from auth menu")
            client.close()
            return False


def create_or_enter_room():
    room = input("Room name: ").strip()
    if not room:
        print("Room name cannot be empty.")
        return
    enter_room(room)


def open_chat():
    address = input("Address to chat with: ").strip()
    if not address:
        print("Address cannot be empty.")
        return
    enter_room(address)


def chat_menu():
    while True:
        print(f"\n--- Logged in as: {client.username} ---")
        print("1. Create/enter room")
        print("2. Open chat")
        print("3. Heartbeat")
        print("4. Exit")

        choice = input("> ").strip()

        if choice == "1":
            create_or_enter_room()

        elif choice == "2":
            open_chat()

        elif choice == "3":
            logger.debug("Sending heartbeat from menu")
            hb = client.heartbeat()
            print("Heartbeat response:", hb)

        elif choice == "4":
            logger.info("User '%s' exited chat menu", client.username)
            client.close()
            break


if auth_menu():
    chat_menu()
