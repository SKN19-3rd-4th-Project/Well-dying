import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'chatbot')))
from src.chatbot import chat

query = "행정안전부 공공서비스혁신과 콜센터 번호"
print(f"Query: {query}")
result = chat(query)

print("\nRetrieved Sources:")
for i, source in enumerate(result['sources'], 1):
    print(f"{i}. {source}")

print("\nAnswer:")
print(result['answer'])
