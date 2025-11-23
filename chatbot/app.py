#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Well Dying 유산상속 상담 챗봇 웹 인터페이스
Streamlit을 사용한 간단한 웹 UI
"""

import streamlit as st
from src.chatbot import chat
import time

# 페이지 설정
st.set_page_config(
    page_title="Well Dying 유산 관련 상담 챗봇 테스트",
    page_icon="💬",
    layout="wide"
)

# 제목
st.title("💬 Well Dying 정보 챗봇")
st.markdown("---")

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 채팅 히스토리 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # 출처 정보 표시 (assistant 메시지인 경우)

# 사용자 입력 처리
if prompt := st.chat_input("궁금한 점을 물어보세요..."):
    # 사용자 메시지 표시
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 세션 ID 생성 (없으면)
    if "thread_id" not in st.session_state:
        import uuid
        st.session_state.thread_id = str(uuid.uuid4())

    # 챗봇 응답 생성
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        with st.spinner("답변을 생성하고 있습니다..."):
            try:
                # RAG 챗봇 호출
                result = chat(prompt, thread_id=st.session_state.thread_id)
                full_response = result['answer']
                
                # 응답 표시
                message_placeholder.markdown(full_response)
            except Exception as e:
                full_response = f"죄송합니다. 오류가 발생했습니다: {str(e)}"
                message_placeholder.markdown(full_response)
        
        # 챗봇 메시지 저장
        st.session_state.messages.append({"role": "assistant", "content": full_response})

# 사이드바
with st.sidebar:
    st.header("ℹ️ 안내")
    st.markdown("""
    **Well Dying 정보 챗봇**에 오신 것을 환영합니다!
    
    이 챗봇은 다음 정보를 기반으로 답변합니다:
    - 유산상속 관련 법률
    - 장례식장 및 장례 절차
    - 정부 지원금
    - 디지털 유산 관리
    
    **사용 방법:**
    1. 아래 입력창에 질문을 입력하세요
    2. 챗봇이 관련 정보를 검색하여 답변합니다
    """)
    
    st.markdown("---")
    
    # 채팅 히스토리 초기화 버튼
    if st.button("🗑️ 대화 기록 지우기"):
        st.session_state.messages = []
        st.rerun()
    
    st.markdown("---")
    st.markdown("**💡 팁:** 구체적인 질문을 하면 더 정확한 답변을 받을 수 있습니다.")

