import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
model_name = "gpt-4o"

class LLMClient:
    """
    모델을 관리하는 클라이언트 클래스
    LangGraph 및 Tool Calling을 지원하기 위해 LangChain 객체를 Wrapping
    """
    def __init__(self, model_name: str = model_name):
        self.model_name = model_name
        self.chat_model = ChatOpenAI(
            api_key=api_key,
            model=model_name, 
            temperature=0.7
        )

    def get_model_with_tools(self, tools: list):
        """
        Tool Calling을 지원하는 모델 객체
        empathy_agent에서 사용
        추후 info_agent에도 사용하도록 확장 예정
        """
        return self.chat_model.bind_tools(tools)
        
    def get_base_model(self):
        """
        Tool 없이 기본 대화만 수행하는 모델 객체
        info_agent 테스트용
        """
        return self.chat_model

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """
        단순 텍스트 생성 메서드
        다이어리 생성(generate_diary_summary)에 사용
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        # invoke()를 사용하여 결과의 content만 추출
        response = self.chat_model.invoke(messages)
        return response.content