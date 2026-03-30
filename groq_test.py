#!/usr/bin/env python3
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = Path(os.getenv("HOTDEAL_ENV_PATH", str(PROJECT_ROOT / ".env")))


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


try:
    from groq import Groq
except ImportError as exc:
    raise SystemExit("groq package is not installed. Install it with: pip install groq") from exc


load_dotenv(ENV_PATH)
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise SystemExit("GROQ_API_KEY is not set")

client = Groq(api_key=api_key)
completion = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "안녕하세요. 오늘은 어떠세요?"},
        {"role": "user", "content": "오늘 기분이 어때 보여?"},
    ],
    temperature=1,
    max_completion_tokens=256,
    top_p=1,
    stream=True,
    stop=None,
)

for chunk in completion:
    print(chunk.choices[0].delta.content or "", end="")
