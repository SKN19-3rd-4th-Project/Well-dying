import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'chatbot')))
from src.chatbot import chat

query = "행정안전부 공공서비스혁신과 콜센터 번호 알려줘"
print(f"Query: {query}")

result = chat(query, n_results=10)

print("\nRetrieval Results:")
found = False
for i, source in enumerate(result['sources'], 1):
    print(f"{i}. {source.get('source')} - {source.get('title')}")
    # Check if the text contains the phone number
    # We need to access the document text, but chat() only returns answer and sources (metadata).
    # Let's modify chat() temporarily or just check the answer.
    
print(f"\nAnswer: {result['answer']}")

if "1588-2188" in result['answer']:
    print("\n[SUCCESS] The phone number was found in the answer.")
else:
    print("\n[FAILURE] The phone number was NOT found in the answer.")
