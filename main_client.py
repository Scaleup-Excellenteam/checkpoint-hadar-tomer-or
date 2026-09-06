from client import ChatClient

server_ip = input("Server IP [press Enter for 127.0.0.1]: ").strip() or "127.0.0.1"

while True:
    username = input("Enter your username: ").strip()
    if username:
        break
    print("Username cannot be empty.")

client = ChatClient(host=server_ip, port=9000, username=username)

while True:
    print(f"\n--- Logged in as: {client.username} ---")
    print("1. Start chat (set target)")
    print("2. Send message")
    print("3. Receive message")
    print("4. Heartbeat")
    print("5. Exit")

    choice = input("> ").strip()

    if choice == "1":
        target = input("Target username / group address: ").strip()
        response = client.start_chat(target)
        print(f"Chat target set to: {response.get('chatting_with')}")

    elif choice == "2":
        chat_id = input("Chat ID / Address (press Enter to use target): ").strip()
        message = input("Message: ")
        client.send_message(chat_id, message)
        print("Message sent!")

    elif choice == "3":
        print("Waiting for messages (press Ctrl+C to cancel)...")
        message = client.receive_message()
        print("Received:", message)

    elif choice == "4":
        hb = client.heartbeat()
        print("Heartbeat response:", hb)

    elif choice == "5":
        client.close()
        break