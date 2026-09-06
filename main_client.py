from client import ChatClient

server_ip = input("Server IP [press Enter for 127.0.0.1]: ").strip() or "127.0.0.1"

while True:
    username = input("Enter your username: ").strip()
    if username:
        break
    print("Username cannot be empty.")

client = ChatClient(host=server_ip, port=9000, username=username)

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


while True:
    print(f"\n--- Logged in as: {client.username} ---")
    print("1. Create/enter room")
    print("2. Heartbeat")
    print("3. Exit")

    choice = input("> ").strip()

    if choice == "1":
        room = input("Room / username: ").strip()
        enter_room(room)

    elif choice == "2":
        hb = client.heartbeat()
        print("Heartbeat response:", hb)

    elif choice == "3":
        client.close()
        break
