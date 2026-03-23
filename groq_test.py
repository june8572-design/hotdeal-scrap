#!/usr/bin/env python3
import os
from groq import Groq

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise SystemExit("GROQ_API_KEY is not set")

client = Groq(api_key=api_key)
completion = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
      {"role": "user", "content": "안녕"},
      {"role": "assistant", "content": "안녕하세요. 오늘은 어떠세요?"},
      {"role": "user", "content": ""}
    ],
    temperature=1,
    max_completion_tokens=1024,
    top_p=1,
    stream=True,
    stop=None
)

for chunk in completion:
    print(chunk.choices[0].delta.content or "", end="")
