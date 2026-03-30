#!/usr/bin/env python3
import json
import os
import sqlite3
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("HOTDEAL_DB_PATH", str(PROJECT_ROOT / "hotdeal.db")))
ENV_PATH = Path(os.getenv("HOTDEAL_ENV_PATH", str(PROJECT_ROOT / ".env")))
MODEL = "llama-3.3-70b-versatile"
API_URL = "https://api.groq.com/openai/v1/chat/completions"

PROMPT_PREFIX = (
    "상품 정보를 1~2문장으로 간단히 요약해줘. 가격/구매처/핵심 특징을 포함하고 제품명은 포함하지마, "
    "과장 없이 존댓말고 담백하게 써줘. ai 티가 절대 나면 안되."
)


def build_prompt(row: sqlite3.Row) -> str:
    parts = [PROMPT_PREFIX]
    if row["price_summary"]:
        parts.append(f"가격요약: {row['price_summary']}")
    if row["details_text_clean"]:
        details = row["details_text_clean"]
        if len(details) > 400:
            details = details[:400] + "..."
        parts.append(f"상세설명: {details}")
    return "\n".join(parts)


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


def call_groq(prompt: str) -> str:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is not set (set env var or .env file)")

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 256,
        "temperature": 0.3,
        "top_p": 0.9,
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, price_summary, details_text_clean
        FROM deals
        WHERE site IN ('네이버', '네이버쇼핑')
          AND details_text_clean IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row is None:
        raise SystemExit("No eligible deal found")

    prompt = build_prompt(row)
    text = call_groq(prompt)
    print(f"[ID {row['id']}] {text}")


if __name__ == "__main__":
    main()
