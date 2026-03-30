#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = Path(os.getenv("HOTDEAL_ENV_PATH", str(PROJECT_ROOT / ".env")))
API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


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


def call_groq(messages: list[dict]) -> str:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is not set")

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_completion_tokens": 256,
        "temperature": 0.7,
        "top_p": 1,
        "stream": False,
    }

    cmd = [
        "curl",
        "-sS",
        "-H",
        f"Authorization: Bearer {api_key}",
        "-H",
        "Content-Type: application/json",
        "-H",
        "Accept: application/json",
        "-d",
        json.dumps(payload, ensure_ascii=False),
        API_URL,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "curl failed")

    data = json.loads(result.stdout)
    if data.get("error"):
        raise SystemExit(str(data["error"]))

    choices = data.get("choices") or []
    if not choices:
        raise SystemExit("No choices returned from Groq API")

    text = choices[0].get("message", {}).get("content", "").strip()
    if not text:
        raise SystemExit("Empty content returned from Groq API")
    return text


def main() -> None:
    messages = [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "안녕하세요. 오늘은 어떠세요?"},
        {"role": "user", "content": "오늘 기분이 어때 보여?"},
    ]
    print(call_groq(messages))


if __name__ == "__main__":
    main()
