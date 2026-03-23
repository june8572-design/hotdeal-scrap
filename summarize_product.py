#!/usr/bin/env python3
import json, sqlite3, subprocess
from pathlib import Path

DB_PATH = Path('/root/.codex/worktrees/aafa/root/hotdeal.db')
API_KEY = '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'
MODEL = 'llama-3.3-70b-versatile'

PROMPT_PREFIX = (
    "상품 정보를 1~2문장으로 간단히 요약해줘. 가격/구매처/핵심 특징을 포함하고 제품명은 포함하지마, "
    "과장 없이 존댓말고 담백하게 써줘. ai 티가 절대 나면 안되."
)


def build_prompt(row):
    parts = [PROMPT_PREFIX]
    parts.append(f"가격요약: {row['price_summary']}")
    if row['details_text_clean']:
        details = row['details_text_clean']
        if len(details) > 400:
            details = details[:400] + "..."
        parts.append(f"상세설명: {details}")
    return "\n".join(parts)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute(
    """
    SELECT id, price_summary, details_text_clean
    FROM deals
    WHERE site IN ('네이버', '네이버쇼핑') AND details_text_clean IS NOT NULL
    ORDER BY created_at DESC
    LIMIT 1
    """
)
row = cur.fetchone()

prompt = build_prompt(row)

payload = {
    "model": MODEL,
    "messages": [{"role": "user", "content": prompt}],
    "max_completion_tokens": 256,
    "temperature": 0.3,
    "top_p": 0.9,
    "stream": False
}

cmd = [
    'curl', '-sS',
    '-H', f'Authorization: Bearer {API_KEY}',
    '-H', 'Content-Type: application/json',
    '-H', 'Accept: application/json',
    '-d', json.dumps(payload),
    'https://api.groq.com/openai/v1/chat/completions'
]

res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode != 0:
    raise SystemExit(res.stderr)

data = json.loads(res.stdout)
text = data['choices'][0]['message']['content'].strip()
print(f"[ID {row['id']}] {text}")
