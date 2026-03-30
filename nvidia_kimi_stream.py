#!/usr/bin/env python3
import json
import os
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = Path(os.getenv("HOTDEAL_ENV_PATH", str(PROJECT_ROOT / ".env")))
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
STREAM = True


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


load_dotenv(ENV_PATH)
api_key = os.getenv("NVIDIA_API_KEY")
if not api_key:
    raise SystemExit("NVIDIA_API_KEY is not set")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "text/event-stream" if STREAM else "application/json",
    "Content-Type": "application/json",
}

payload = {
    "model": "moonshotai/kimi-k2.5",
    "messages": [
        {
            "role": "user",
            "content": "제품 홍보글 재가공 해줘. 절대 ai 스럽지 않게 사람이 가볍게 홍보하는투의 글이어야 해. 내가 제공하는 정보 1. 제품명 블랙라벨 오렌지 중소과 20과 3kg 2. 가격요약 네이버의 11,510원이 가장 저렴하며, 다른 쇼핑몰 대비 약 3,000~9,000원 저렴합니다. 네이버 구매를 추천합니다. 3. 제품홍보글 개당 575원꼴 나옴\n블랙라벨이라 맛 괜찮음\n2개 주문하면 3과 더줌",
        }
    ],
    "max_tokens": 2048,
    "temperature": 1.0,
    "top_p": 1.0,
    "stream": STREAM,
}

req = urllib.request.Request(
    INVOKE_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers=headers,
    method="POST",
)

with urllib.request.urlopen(req, timeout=120) as resp:
    if STREAM:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            content = delta.get("content")
            if content:
                print(content, end="", flush=True)
    else:
        print(resp.read().decode("utf-8", errors="replace"))
