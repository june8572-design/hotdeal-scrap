# Handover

**Workspace**
- /root/.codex/worktrees/aafa/root

**Goal Summary**
- Crawl hotdeal.zip deals into SQLite.
- Enrich Naver/NaverShopping items by visiting detail pages and extracting price comparison table, price summary, detail text, and image URLs.
- Generate promo text via NVIDIA API (Kimi) with strict prompt control.
- Summarize product info via Groq API (llama-3.3-70b-versatile) using a fixed prompt (1–2 sentences, no product name, plain tone).

**Key Files**
- /root/.codex/worktrees/aafa/root/hotdeal.db
- /root/.codex/worktrees/aafa/root/enrich_hotdeal_details.py
- /root/.codex/worktrees/aafa/root/generate_promo_from_db.py
- /root/.codex/worktrees/aafa/root/nvidia_kimi_stream.py
- /root/.codex/worktrees/aafa/root/groq_test.py
- /root/.codex/worktrees/aafa/root/summarize_product.py

**Database Schema (SQLite: deals table)**
- Base fields from API: id (PK), title, price, category, site, created_at, views, thumbnail_url, seo_url, post_url, time, relative_time, relative_time_class, favicon_url, community_name, gradient
- Added enrichment fields: price_table_json, price_summary, details_text_raw, details_text_clean, details_images_json, details_fetched_at
- Added promo fields: promo_text, promo_generated_at

**Data Sources**
- Listing API: https://hotdeal.zip/api/deals.php?page=1&category=all&_t=0
- Detail page: https://hotdeal.zip/<seo_url>
- The detail page includes:
- Deal header (title/category/date/site/original post link)
- Price box (price, buy link)
- Price comparison table (HTML table inside ai-price-content)
- Price summary (div.price-summary)
- Product details section (div.product-details) with text + images

**API Notes**
- hotdeal.zip API may require a User-Agent header; curl with -A 'Mozilla/5.0' worked.
- Detail pages may require URL-encoding of seo_url.

**Scripts and What They Do**

1) /root/.codex/worktrees/aafa/root/enrich_hotdeal_details.py
- Adds columns if missing.
- For site in (네이버, 네이버쇼핑), fetches detail page and stores:
- price_table_json (list of seller/product/price/note)
- price_summary (text)
- details_text_raw (HTML stripped)
- details_text_clean (normalized, removes "📝 상품 정보")
- details_images_json (list of image URLs)
- details_fetched_at timestamp
- Uses URL-encoding for seo_url.

2) /root/.codex/worktrees/aafa/root/generate_promo_from_db.py
- Builds prompt from DB and calls NVIDIA Kimi via curl.
- Current prompt prefix (latest):
- 제품 홍보글 재가공 해줘. 홍보글의 전개는 "어떤 제품이 특가가 떴는데 어떻게 싸고, 제품이 어떤 장점으로 추천하는 이유"를 적는 흐름으로 가자. 절대 ai 스럽지 않게 사람이 가볍게 홍보하는투의 글이어야 해. 존댓말로 작성. 이모지 금지. 필수사항, 반드시 2~3 문장으로만 작성해줘. 다른 문장 추가 금지. 내가 제공하는 정보
- Adds product name, price summary, details_text_clean (truncated to 400 chars).
- Calls NVIDIA endpoint: https://integrate.api.nvidia.com/v1/chat/completions
- Recommended stable settings for Kimi when using this prompt:
- model: moonshotai/kimi-k2.5
- temperature: 0.2
- top_p: 0.8
- max_tokens: 256
- chat_template_kwargs: {"thinking": false}
- Known behavior: Without thinking=false, model sometimes returns reasoning only or ignores sentence count.

3) /root/.codex/worktrees/aafa/root/nvidia_kimi_stream.py
- Streamed Kimi output and prints only content delta.
- Handles empty choices and [DONE].

4) /root/.codex/worktrees/aafa/root/summarize_product.py
- Uses Groq API to summarize latest Naver/NaverShopping item (1 row).
- Current fixed prompt (final):
- 상품 정보를 1~2문장으로 간단히 요약해줘. 가격/구매처/핵심 특징을 포함하고 제품명은 포함하지마, 과장 없이 존댓말고 담백하게 써줘. ai 티가 절대 나면 안되.
- Payload sent to: https://api.groq.com/openai/v1/chat/completions
- model: llama-3.3-70b-versatile
- max_completion_tokens: 256, temperature: 0.3, top_p: 0.9

5) /root/.codex/worktrees/aafa/root/groq_test.py
- Simple streaming test for Groq SDK.
- Requires venv /root/.venv and GROQ_API_KEY.

**Environment Setup**
- Python venv created at /root/.venv
- Installed package: groq (inside venv)
- GROQ API key used in tests via env: GROQ_API_KEY
- NVIDIA key used via env in scripts (hardcoded in some ad-hoc runs; should move to env in production)

**Most Recent Successful Outputs (samples)**
- Groq summary (1–2 sentences, no product name):
- 네이버에서 29,900원에 구매할 수 있으며, 미스터키다리에서는 39,900원에 무료배송을 제공합니다. 액티포닌이 함유된 젤리형 다이어트 보조제로, 체지방 감소와 혈당 관리에 도움을 줄 수 있습니다.

**Known Issues / Observations**
- Kimi thinking models can return reasoning only (content null). Use non-thinking model + thinking=false.
- Sentence-count constraints are not perfectly obeyed without post-processing.
- Detail page parsing is regex-based; robust enough for current HTML but may break if layout changes.

**Next Steps (Suggested)**
- If strict sentence count is required, add post-processing that truncates to 1–2 or 2–3 sentences.
- Move API keys to environment variables in all scripts (remove hardcoded keys).
- Add retry/backoff for API calls and rate limiting.
- Optionally store summary outputs in DB (new columns) if needed.
