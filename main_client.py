from client import ChatClient

server_ip = input("Server IP [press Enter for 127.0.0.1]: ").strip() or "127.0.0.1"

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

    print(f"--- History with {room} ---")
    for chat_id, sender, direction, message, timestamp in client.get_history(room):
        who = "you" if direction == "sent" else sender
        print(f"[{timestamp}] {who}: {message}")

    print(f"--- Live chat with {room} (type /leave to go back) ---")
    while True:
        text = input("> ")
        if text == "/leave":
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
            if client.signup(username, password):
                print("Signup successful. You can now log in.")
            else:
                print("Signup failed (username may already be taken).")

        elif choice == "2":
            username = input("Username: ").strip()
            password = input("Password: ").strip()
            if client.login(username, password):
                print(f"Logged in as {client.username}")
                return True
            else:
                print("Login failed.")

        elif choice == "3":
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
            hb = client.heartbeat()
            print("Heartbeat response:", hb)

        elif choice == "4":
            client.close()
            break


if auth_menu():
    chat_menu()
