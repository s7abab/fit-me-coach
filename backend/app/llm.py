from functools import lru_cache
from openai import OpenAI
from app.config import settings

@lru_cache
def get_client():
    # Create the client once and reuse it for every request
    return OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

def chat(messages, temperature=0.2):
    res = get_client().chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=temperature,
    )
    return res.choices[0].message.content