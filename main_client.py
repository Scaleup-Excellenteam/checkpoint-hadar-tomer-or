from client import ChatClient

client = ChatClient("127.0.0.1", 5000)

current_room = None


def on_message(chat_id, message):
    # Only interrupt the screen with messages for the room we're currently in.
    if chat_id == current_room:
        print(f"\n{chat_id}: {message}")


client.set_message_handler(on_message)


def enter_room(room):
    global current_room
    current_room = room

    response = client.start_chat(room)
    print(response)

    print(f"--- History with {room} ---")
    for chat_id, direction, message, timestamp in client.get_history(room):
        who = "you" if direction == "sent" else chat_id
        print(f"[{timestamp}] {who}: {message}")

    print(f"--- Live chat with {room} (type /leave to go back) ---")
    while True:
        text = input("> ")
        if text == "/leave":
            break
        client.send_message(room, text)

    current_room = None


while True:
    print("\n1. Create/enter room")
    print("2. Exit")

    choice = input("> ")

    if choice == "1":
        room = input("Room / username: ")
        enter_room(room)

    elif choice == "2":
        client.close()
        break