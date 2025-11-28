import sys
import os

# Add current directory to sys.path just in case
sys.path.append(os.getcwd())

try:
    print("Attempting to import ConversationEngine...")
    from conversation_engine import ConversationEngine
    print("Import successful!")
    
    print("Attempting to initialize ConversationEngine...")
    engine = ConversationEngine()
    print("Initialization successful!")
    
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
