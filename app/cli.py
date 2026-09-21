import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import PROJECT_ROOT  # noqa: E402
from app.chatbot.nl2sql import NL2SQLChatbot  # noqa: E402

documents_dir = str(PROJECT_ROOT / "data")
print("documents_dir: ", documents_dir)

# Initialize the chatbot
chatbot = NL2SQLChatbot(
    documents_dir=documents_dir  # Directory containing all documentation files
)


def chat_loop():
    print("NL2SQL Chatbot initialized. Type 'exit/退出' to quit.")
    print("Special commands:")
    print("  - 'add_doc [path]': Add a new document to the knowledge base")

    while True:
        try:
            user_input = input("\nYour query: ").strip()
            if user_input.lower() == "exit" or user_input.lower() == "退出":
                print("Exiting chatbot...")
                sys.exit(0)  # 确保退出程序

            if user_input.startswith("add_doc "):
                doc_path = user_input[8:].strip()
                result = chatbot.add_document(doc_path)
                print(f"\nResult: {result}\n")
                continue

            response = chatbot.process_query(user_input)
            print(f"\nChatbot: {response}\n")
        except (KeyboardInterrupt, EOFError):
            print("\nUser interrupted. Exiting chatbot...")
            sys.exit(0)


if __name__ == "__main__":
    chat_loop()
