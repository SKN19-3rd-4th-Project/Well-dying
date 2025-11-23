import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

try:
    indexes = pc.list_indexes()
    print("Existing Indexes:")
    for index in indexes:
        print(f"- {index.name}")
except Exception as e:
    print(f"Error listing indexes: {e}")
