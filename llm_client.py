import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
model_name = "gpt-4o"


class LLMClient:
    """Wrapper around LangChain ChatOpenAI for tool and plain chat."""

    def __init__(self, model_name: str = model_name):
        self.model_name = model_name
        self.chat_model = ChatOpenAI(api_key=api_key, model=model_name, temperature=0.7)

    def get_model_with_tools(self, tools: list):
        """Model instance with tool bindings enabled."""
        return self.chat_model.bind_tools(tools)

    def get_base_model(self):
        """Base chat model without tool bindings."""
        return self.chat_model

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """Simple text generation helper (used for diary summarization)."""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self.chat_model.invoke(messages)
        return response.content
