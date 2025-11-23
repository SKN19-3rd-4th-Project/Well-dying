import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'chatbot')))
from src.chatbot import chat

query = "유산 관련해서 물어보고싶은데어디에 전화해?"
print(f"Query: {query}")

result = chat(query, n_results=5)

print("\nRetrieval Results:")
for i, source in enumerate(result['sources'], 1):
    print(f"{i}. {source.get('source')} - {source.get('title')}")

print(f"\nAnswer: {result['answer']}")

if "1588-2188" in result['answer']:
    print("\n[SUCCESS] The phone number was found.")
else:
    print("\n[FAILURE] The phone number was NOT found.")
