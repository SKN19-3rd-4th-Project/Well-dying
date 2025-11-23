import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

try:
    indexes = pc.list_indexes()
    print("Index Details:")
    for index in indexes:
        desc = pc.describe_index(index.name)
        print(f"- Name: {index.name}, Dimension: {desc.dimension}, Status: {desc.status['state']}")
except Exception as e:
    print(f"Error checking indexes: {e}")
