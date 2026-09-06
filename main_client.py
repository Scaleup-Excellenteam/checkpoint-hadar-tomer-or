from client import ChatClient

client = ChatClient("127.0.0.1", 5000)

while True:
    print("\n1. Start chat")
    print("2. Send message")
    print("3. Receive message")
    print("4. Exit")

    choice = input("> ")

    if choice == "1":
        username = input("Username: ")
        response = client.start_chat(username)
        print(response)

    elif choice == "2":
        chat_id = input("Chat ID: ")
        message = input("Message: ")

        client.send_message(chat_id, message)

    elif choice == "3":
        message = client.receive_message()
        print(message)

    elif choice == "4":
        client.close()
        break