# llm_client.py

from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv()


api_key = os.getenv("OPENAI_API_KEY")


client = OpenAI(api_key=api_key)


def generate_text(system_prompt: str, user_prompt: str, model: str = "gpt-4o-mini") -> str:

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()
