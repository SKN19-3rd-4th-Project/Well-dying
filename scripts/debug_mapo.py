import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'chatbot')))
from src.chatbot import chat

query = "마포구 장례식장 알려줘"
print(f"Query: {query}")
result = chat(query)

print("\nRetrieved Sources:")
for i, source in enumerate(result['sources'], 1):
    print(f"{i}. {source}")

print("\nAnswer:")
print(result['answer'])
