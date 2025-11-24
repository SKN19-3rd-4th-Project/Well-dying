import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
# 기존 import 유지
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

class LLMClient:
    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        # LangChain 클라이언트
        self.chat_model = ChatOpenAI(model=model_name, temperature=0.7, api_key=api_key)

    # ---------------------------------------------------------
    # [Legacy] 기존 함수 보존
    # ---------------------------------------------------------
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """기존의 단순 텍스트 생성 함수"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        response = self.chat_model.invoke(messages)
        return response.content

    # ---------------------------------------------------------
    # [New] LangGraph용 메서드
    # ---------------------------------------------------------
    def get_model_with_tools(self, tools: list):
        """Tool이 바인딩된 모델 반환"""
        return self.chat_model.bind_tools(tools)
        
    def get_base_model(self):
        """기본 모델 반환"""
        return self.chat_model