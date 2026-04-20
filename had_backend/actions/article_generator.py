#!/usr/bin/env python3
"""LLM 기반 자동글 생성 모듈.

카테고리별 프롬프트를 사용하여 소스 데이터를 기반으로 글을 생성합니다.
- product: 상품 홍보글
- tip: 꿀팁 공유글
- good: 좋은글/감동글
- fun: 유머글
"""
import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# 카테고리별 프롬프트 템플릿
PROMPT_TEMPLATES = {
    "product": (
        "제품 홍보글을 작성해줘. "
        "\"어떤 제품이 특가가 떴는데 어떻게 싸고, 제품이 어떤 장점으로 추천하는 이유\"를 적는 흐름으로 가자. "
        "절대 AI 스럽지 않게 사람이 가볍게 홍보하는 투의 글이어야 해. 존댓말로 작성. "
        "이모지 금지. 반드시 2~3 문장으로만 작성해줘. 다른 문장 추가 금지."
    ),
    "tip": (
        "아래 생활 꿀팁 정보를 바탕으로 카페에 공유할 꿀팁 글을 작성해줘. "
        "원본 내용을 그대로 복사하지 말고, 자연스럽게 재구성해서 공유하는 느낌으로. "
        "존댓말로 작성. 이모지 금지. 3~5 문장 이내로 간결하게."
    ),
    "good": (
        "아래 내용을 바탕으로 감동적이거나 좋은 글을 작성해줘. "
        "카페에 공유할 만한 따뜻한 메시지 느낌으로. "
        "존댓말로 작성. 이모지 금지. 3~5 문장 이내로."
    ),
    "fun": (
        "아래 재미있는 내용을 바탕으로 유머글을 작성해줘. "
        "카페에 공유할 만한 가벼운 웃음 포인트를 살려서. "
        "존댓말로 작성. 이모지 금지. 3~5 문장 이내로."
    ),
}


def load_dotenv(path: Path) -> None:
    """간단한 .env 로더"""
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


def call_llm(prompt: str, model: str = "moonshotai/kimi-k2.5") -> str:
    """NVIDIA API를 통해 LLM 호출"""
    load_dotenv(ENV_PATH)
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY가 설정되지 않았습니다.")

    api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
        "temperature": 0.4,
        "top_p": 0.9,
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    cmd = [
        "curl", "-sS",
        "-H", f"Authorization: Bearer {api_key}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-d", json.dumps(payload, ensure_ascii=False),
        api_url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "curl failed")

    data = json.loads(result.stdout)
    if data.get("error"):
        raise RuntimeError(str(data["error"]))

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM이 응답을 반환하지 않았습니다.")

    content = choices[0].get("message", {}).get("content", "").strip()
    if not content:
        raise RuntimeError("LLM이 빈 응답을 반환했습니다.")

    return content


def generate_article_from_sources(
    sources: list[dict],
    category: str,
    target_name: str = "",
) -> str:
    """소스 데이터를 기반으로 카테고리에 맞는 글 생성"""
    template = PROMPT_TEMPLATES.get(category, PROMPT_TEMPLATES["tip"])

    # 소스 내용 결합
    source_texts = []
    for i, s in enumerate(sources, 1):
        title = s.get("title", "")
        content = s.get("content_text", "")[:500]  # 너무 긴 내용 절단
        source_texts.append(f"[소스 {i}] {title}\n{content}")

    combined = "\n\n".join(source_texts)

    prompt = f"{template}\n\n---\n\n{combined}"

    return call_llm(prompt)


def process_pending_articles(conn) -> list[dict]:
    """PENDING 상태의 article_queue 항목을 LLM으로 처리"""
    cursor = conn.cursor()

    # 처리 대기 항목 조회
    rows = cursor.execute(
        """SELECT aq.*, t.name as target_name
        FROM article_queue aq
        LEFT JOIN targets t ON aq.target_id = t.id
        WHERE aq.status = 'PENDING'
        ORDER BY aq.created_at ASC
        LIMIT 5"""
    ).fetchall()

    results = []
    for row in rows:
        article_id = row["id"]
        category = row["category"]
        source_ids = json.loads(row["source_ids"] or "[]")
        target_name = row["target_name"] or ""

        try:
            # 소스 조회
            if source_ids:
                placeholders = ",".join("?" * len(source_ids))
                sources = cursor.execute(
                    f"SELECT * FROM article_sources WHERE id IN ({placeholders})",
                    tuple(source_ids)
                ).fetchall()
                source_dicts = [{k: s[k] for k in s.keys()} for s in sources]
            else:
                # 소스 없이 content 사용
                source_dicts = [{"title": row["title"], "content_text": row["content"]}]

            # LLM 글 생성
            generated = generate_article_from_sources(source_dicts, category, target_name)

            # 업데이트
            cursor.execute(
                """UPDATE article_queue
                SET content = ?, status = 'PENDING', updated_at = datetime('now')
                WHERE id = ?""",
                (generated, article_id)
            )
            conn.commit()
            results.append({"article_id": article_id, "status": "generated"})

        except Exception as e:
            cursor.execute(
                """UPDATE article_queue
                SET status = 'ERROR', error_message = ?, updated_at = datetime('now')
                WHERE id = ?""",
                (str(e)[:500], article_id)
            )
            conn.commit()
            results.append({"article_id": article_id, "status": "error", "error": str(e)})

    return results
