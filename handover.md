# Handover - 프로젝트 인계 문서

**최종 업데이트**: 2026-04-19  
**현재 브랜치**: `codex/aafa`

---

## 1. 프로젝트 개요

### 프로젝트 이름
**HAD** (Hotdeal & Cafe Automation Dashboard)

### 핵심 기능
1. **핫딜 수집**: hotdeal.zip에서 딜 정보를 크롤링하여 SQLite DB에 저장
2. **딜 상세 정보 수집**: 네이버/네이버쇼핑 딜의 상세 페이지에서 가격 비교표, 가격 요약, 상품 상세 텍스트/이미지 추출
3. **프로모 글 생성**: NVIDIA Kimi API를 활용하여 AI 홍보글 생성
4. **요약 생성**: Groq API (llama-3.3-70b-versatile)로 상품 정보 1~2문장 요약
5. **브랜드커넥터 링크 발급**: 네이버 쇼핑의 브랜드커넥터 상품 링크 자동 발급 (Playwright 기반)
6. **카페 자동화**: 네이버 카페 자동 댓글 작업 (iwacha 카페 대상)

---

## 2. 디렉토리 구조

```
hotdeal-scrap/
├── .env                    # 환경변수 (API 키 등)
├── .env.example            # 환경변수 템플릿
├── .secrets/               # Playwright 세션 저장소
│   └── naver_bc_state.json # 브랜드커넥터 로그인 세션
├── had_backend/            # 웹 대시보드 백엔드
│   ├── app.py              # FastAPI/Starlette 메인 앱
│   ├── db_init.py          # DB 초기화 스크립트
│   ├── actions/            # 파이프라인 액션 모듈
│   │   ├── __init__.py
│   │   ├── pipeline.py      # 파이프라인 실행 로직
│   │   └── hotdeal_actions.py # 핫딜 관련 함수들
│   └── static/             # 프론트엔드 정적 파일
│       ├── index.html      # 메인 대시보드
│       └── brandconnect.html # 브랜드커넥터 모니터링 페이지
├── hotdeal.db              # SQLite 데이터베이스
├── scripts/               # 운영 스크립트
├── sql/                   # SQL 스키마 파일
├── tests/                 # 테스트 파일들
├── campingfirst_mvp/      # 카페 자동화 관련 코드 (legacy)
│   ├── app.py             # 카페 자동화 메인
│   ├── naver_cafe_adapter.py # 네이버 카페 API 어댑터
│   ├── worker.py          # 워커 프로세스
│   ├── db.py              # 전용 DB 모듈
│   └── config.py          # 설정
├── brandconnect_issue_links.py # 브랜드커넥터 링크 발급 스크립트
├── enrich_hotdeal_details.py  # 딜 상세 정보 수집
├── fetch_hotdeal_list.py       # 핫딜 목록 조회
├── generate_promo_from_db.py  # 프로모 글 생성 (NVIDIA Kimi)
├── summarize_product.py       # 요약 생성 (Groq)
├── todayhumor_dryrun.py        # 오늘의 유머 스크래핑
└── groq_test.py                # Groq API 테스트

```

---

## 3. 데이터베이스 스키마

### SQLite: hotdeal.db

#### deals 테이블 (핫딜 정보)
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | Primary Key |
| title | TEXT | 딜 제목 |
| price | TEXT | 가격 |
| category | TEXT | 카테고리 |
| site | TEXT | 사이트 (네이버, 네이버쇼핑 등) |
| created_at | TEXT | 생성 일시 |
| views | INTEGER | 조회수 |
| thumbnail_url | TEXT | 썸네일 URL |
| seo_url | TEXT | SEO URL |
| post_url | TEXT | 게시글 URL |
| time | TEXT | 시간 정보 |
| relative_time | TEXT | 상대 시간 |
| relative_time_class | TEXT | 시간 클래스 |
| favicon_url | TEXT | 파비콘 URL |
| community_name | TEXT | 커뮤니티 이름 |
| gradient | TEXT | 그래디언트 스타일 |
| fetched_at | TEXT | 수집 일시 |
| price_table_json | TEXT | 가격 비교표 (JSON) |
| price_summary | TEXT | 가격 요약 |
| details_text_raw | TEXT | 상세 텍스트 (원본) |
| details_text_clean | TEXT | 상세 텍스트 (정제됨) |
| details_images_json | TEXT | 상세 이미지 URLs (JSON) |
| details_fetched_at | TEXT | 상세 수집 일시 |
| promo_text | TEXT | AI 홍보글 |
| promo_generated_at | TEXT | 홍보글 생성 일시 |
| brand_connector_link | TEXT | 브랜드커넥터 링크 |
| brand_connector_status | TEXT | 발급 상태 (success/failed/pending) |
| brand_connector_error | TEXT | 오류 메시지 |
| brand_connector_generated_at | TEXT | 링크 발급 일시 |
| brand_connector_retry_count | INTEGER | 재시도 횟수 |
| brand_connector_last_attempt | INTEGER | 마지막 시도 타임스탬프 |

#### presets 테이블 (수집 프리셋)
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | Primary Key |
| name | TEXT | 프리셋 이름 |
| target_url | TEXT | 대상 URL |
| action_type | TEXT | 액션 타입 (PROMO) |
| interval_min | INTEGER | 실행 주기 (분) |
| needs_confirmation | INTEGER | 승인 필요 여부 (1=예) |
| is_active | INTEGER | 활성화 여부 |
| created_at | DATETIME | 생성 일시 |
| updated_at | DATETIME | 업데이트 일시 |

#### targets 테이블 (카페 타겟)
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | Primary Key |
| name | TEXT | 타겟 이름 |
| site_type | TEXT | 사이트 타입 |
| target_url | TEXT | 대상 URL |
| cafe_id | TEXT | 카페 ID |
| menu_id | TEXT | 메뉴 ID |
| activity_type | TEXT | 활동 타입 (COMMENT 등) |
| daily_limit | INTEGER | 일일 실행 횟수 제한 |
| is_active | INTEGER | 활성화 여부 |
| created_at | DATETIME | 생성 일시 |

#### jobs 테이블 (작업 대기열)
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | Primary Key |
| target_id | INTEGER | FK -> targets.id |
| preset_id | INTEGER | FK -> presets.id |
| job_type | TEXT | 작업 타입 (HOTDEAL/CAFE) |
| status | TEXT | 상태 (PENDING/APPROVED/REJECTED) |
| post_title | TEXT | 게시글 제목 |
| post_url | TEXT | 게시글 URL |
| content | TEXT | 작업 내용 (댓글 등) |
| error_message | TEXT | 오류 메시지 |
| created_at | DATETIME | 생성 일시 |
| updated_at | DATETIME | 업데이트 일시 |

#### logs 테이블 (실행 로그)
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | Primary Key |
| level | TEXT | 로그 레벨 (INFO/ERROR/WARNING) |
| message | TEXT | 메시지 |
| details | TEXT | 상세 정보 |
| created_at | DATETIME | 생성 일시 |

#### comment_pool 테이블 (댓글 저장소)
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INTEGER | Primary Key |
| content | TEXT | 댓글 내용 |
| created_at | DATETIME | 생성 일시 |

---

## 4. 백엔드 아키텍처

### had_backend/app.py (Starlette/FastAPI)

**주요 API 엔드포인트**:

| 메서드 | 엔드포인트 | 설명 |
|--------|------------|------|
| GET | `/` | 메인 대시보드 (index.html) |
| GET | `/brandconnect` | 브랜드커넥터 페이지 (brandconnect.html) |
| GET | `/naver` | 네이버 스토어 딜 조회 (naver.html) |
| GET | `/api/v1/stats` | 통합 통계 |
| GET/POST | `/api/v1/presets` | 프리셋 조회/생성 |
| DELETE/PATCH | `/api/v1/presets/{id}` | 프리셋 삭제/토글 |
| GET/POST | `/api/v1/targets` | 카페 타겟 조회/생성 |
| DELETE | `/api/v1/targets/{id}` | 타겟 삭제 |
| GET | `/api/v1/jobs` | 작업 대기열 조회 (status 필터 지원) |
| POST | `/api/v1/jobs/{id}/approve` | 작업 승인 |
| POST | `/api/v1/jobs/{id}/reject` | 작업 거부 |
| GET | `/api/v1/logs` | 실행 로그 조회 |
| GET | `/api/v1/deals` | 딜 목록 조회 |
| POST | `/api/v1/pipelines/run` | 파이프라인 즉시 실행 |
| GET | `/api/v1/naver/deals` | 네이버 스토어 딜 조회 (페이지네이션) |
| POST | `/api/v1/naver/generate-links` | 선택 딜 링크 생성 요청 |
| GET | `/api/v1/brandconnect/stats` | 브랜드커넥터 통계 |
| GET | `/api/v1/brandconnect/list` | 브랜드커넥터 목록 (status 필터) |
| POST | `/api/v1/brandconnect/retry/{deal_id}` | 링크 발급 재시도 |

**특징**:
- Lazy Import 적용: `run_all_pipelines`는 API 호출 시점에만 import
- DB 경로: `/home/luisuh/hotdeal-scrap/hotdeal.db` (하드코딩)

### had_backend/actions/pipeline.py

**PipelineRunner 클래스**:
- `process_hotdeal_presets()`: 활성화된 핫딜 프리셋 처리
  1. 최신 딜 조회 (fetch_latest_deals)
  2. DB 저장 (save_deals_to_db)
  3. 딜 상세 정보 수집 (enrich_deal)
  4. 프로모 글 생성 (generate_promo_text)
  5. 작업 대기열 생성 (PENDING 상태)
  
- `process_cafe_targets()`: 활성화된 카페 타겟 처리 (현재 미구현)

**실행 함수**:
- `run_all_pipelines()`: 전체 파이프라인 실행 (POST /api/v1/pipelines/run 호출 시)

### had_backend/actions/hotdeal_actions.py

**핵심 함수**:

| 함수 | 설명 |
|------|------|
| `fetch_latest_deals(category, page)` | hotdeal.zip API에서 딜 목록 조회 |
| `save_deals_to_db(deals)` | 딜 목록을 DB에 저장 (INSERT OR IGNORE) |
| `enrich_deal(deal_id)` | 딜 상세 페이지 파싱 및 저장 |
| `generate_promo_text(deal_id)` | NVIDIA Kimi API로 프로모 글 생성 |
| `get_conn()` | DB 커넥션 반환 |

**상세 파싱 로직**:
- `_fetch_html(url)`: 딜 상세 페이지 HTML 가져오기
- `_html_to_text(s)`: HTML → 텍스트 변환
- `_clean_text(s)`: 텍스트 정제
- `_parse_page(html_text)`: 가격 요약, 상세 텍스트 추출

---

## 5. 프론트엔드 아키텍처

### had_backend/static/index.html

**구성 요소**:
1. **헤더**: 프로젝트 제목, 스케줄러 상태, 브랜드커넥터 링크, 사용 가이드, 즉시 실행 버튼
2. **상단 통계 카드**: 활성 프리셋, 카페 타겟, 승인 대기, 전체 딜 수, 브랜드커넥터 통계
3. **좌측 패널**: 수집 설정 (hotdeal.zip 토글), 카페 활동 목록
4. **우측 패널**: 통합 작업 대기열, 실행 로그
5. **하단 섹션**: 수집된 핫딜 목록 테이블

**주요 JavaScript 함수**:
- `fetchStats()`: 통계 조회
- `fetchBCStats()`: 브랜드커넥터 통계 조회
- `fetchHotdealPreset()`: hotdeal.zip 프리셋 상태 조회
- `toggleHotdealPreset()`: 프리셋 활성화 토글
- `fetchTargets()`: 카페 타겟 목록 조회
- `fetchJobs()`: 작업 대기열 조회
- `fetchLogs()`: 실행 로그 조회
- `fetchDeals()`: 딜 목록 조회
- `runPipelines()`: 파이프라인 즉시 실행
- `approveJob()`/`rejectJob()`: 작업 승인/거부
- `refresh()`: 전체 데이터 새로고침 (15초 간격)

### had_backend/static/brandconnect.html

**구성 요소**:
1. 상단 통계 카드: 전체/성공/실패/대기 건수, 성공률
2. 진행 상황 테이블: deal_id, 제품명, 사이트, 상태, 링크, 재시도 횟수, 마지막 시도 시각
3. 실패 로그 섹션
4. 수동 재시도 버튼
5. 15초 자동 새로고침

---

## 6. 핵심 스크립트

### brandconnect_issue_links.py (1269줄)
- **목적**: 네이버 브랜드커넥터 상품 링크 자동 발급
- **입력**: DB의 네이버/네이버쇼핑 딜 (out_links_json 포함)
- **출력**: brand_connector_link, brand_connector_status 업데이트
- **옵션**:
  - `--deal-id`: 특정 딜만 처리 (단일, 콤마, 범위 지원)
  - `--manual-login-only`: 로그인만 수행
  - `--login-only`: 로그인 후 종료
- **파이프라인 (v2 - out_links 기반)**:
  1. DB에서 네이버 딜 로드 (out_links_json 포함, 5-tuple)
  2. `parse_out_links()`: out_links_json → 링크 리스트
  3. `find_affiliate_link()`: 제휴 링크 탐색
     - brandconnect 링크 → 그대로 저장 (추가 작업 불필요)
     - naver.me 링크 → `fetch_real_product_info()`로 접속 → og:title에서 상품명 재수집
  4. 제휴 링크 없으면 → `classify_all_links()`로 비제휴 분류 (건너뜀)
  5. 재수집된 상품명으로 브랜드커넥터 검색 → 링크 발급
  6. Playwright로 브라우저 실행, 세션 로드, 수동 로그인 대기
  7. 상품명 검색 → 결과 클릭 → "링크 발급" 버튼 → 링크 추출
  8. DB 저장

#### 제휴/비제휴 분류 로직 상세 (`classify_link`)

**분류 함수 체인**:
- `classify_link(url)` → (is_affiliate_candidate, url_type): 단일 URL 분류
- `classify_all_links(out_links)` → 전체 링크 중 대표 분류 (제휴 > 비제휴 > 미분류)
- `find_affiliate_link(out_links)` → 제휴 링크 찾아서 상품명까지 수집
- `parse_out_links(json_str)` → out_links_json 문자열 파싱
- `fetch_real_product_info(url)` → naver.me 접속하여 (상품명, 최종URL) 반환
- `_extract_product_name_from_html(html)` → HTML에서 og:title 추출

**분류 규칙** (우선순위 순):

| 순서 | 패턴 | 분류 | url_type | 비고 |
|------|------|------|----------|------|
| 1 | `brandconnect.naver.com` + `/affiliate/` 또는 `/affiliates/` | 제휴(1) | brandconnect | 이미 BC 제휴 링크 |
| 2 | `naver.me/` | 제휴(1) | naver_me | 리다이렉트 → 실제 URL 추적 필요 |
| 3 | `m.brand.naver.com/` | 비제휴(0) | m_brand_store | 모바일 브랜드스토어 |
| 4 | `m.smartstore.naver.com/` | 비제휴(0) | m_smartstore | 모바일 스마트스토어 |
| 5 | `smartstore.naver.com/` | 비제휴(0) | smartstore | 데스크톱 스마트스토어 |
| 6 | `brand.naver.com/` | 비제휴(0) | brand_store | 브랜드스토어 |
| 7 | `shopping.naver.com/` | 비제휴(0) | shopping | 네이버쇼핑 |
| - | 기타 | 미분류(None) | unknown | 매칭 안 됨 |

**백데이터 분석 결과 (60건 네이버 딜 기준)**:
- 제휴: 2건 (3.3%) — naver.me 2건
- 비제휴: 55건 (91.7%) — smartstore 23, brand.naver 24, m.smartstore 4, shopping 3, m.brand 1
- no_links: 3건 (5.0%)

**⚠️ 검증 필요 사항**:
- 분류 로직이 URL 패턴 기반이라 100% 신뢰 불가
- naver.me 리다이렉트 최종 URL 검증 필요
- 비제휴로 분류된 링크 중 실제 제휴 가능한 상품 존재 여부 확인 필요
- 검증 스크립트: `scripts/verify_outlinks_classification.py` (구현 예정)

### enrich_hotdeal_details.py
- **목적**: 딜 상세 페이지에서 정보 추출
- **대상**: site = '네이버' 또는 '네이버쇼핑'
- **추출 정보**: price_table_json, price_summary, details_text_clean, details_images_json

### generate_promo_from_db.py
- **목적**: NVIDIA Kimi API로 프로모 글 생성
- **모델**: moonshotai/kimi-k2.5
- **설정**: temperature=0.2, top_p=0.8, max_tokens=256

### summarize_product.py
- **목적**: Groq API로 상품 정보 요약
- **모델**: llama-3.3-70b-versatile
- **프롬프트**: "상품 정보를 1~2문장으로 간단히 요약해줘..."

### fetch_hotdeal_list.py
- **목적**: hotdeal.zip API에서 딜 목록 조회
- **출력**: JSON 데이터

### todayhumor_dryrun.py
- **목적**: 오늘의 유머에서 꿀팁/유머 게시글 수집
- **기능**: 137개 게시판 탐색, 점수 기반 필터링, 키워드 매칭
- **저장**: SQLite 또는 출력

---

## 7. 환경 설정

### 필수 환경변수 (.env)
```
NVIDIA_API_KEY=...
GROQ_API_KEY=...
HOTDEAL_DB_PATH=/home/luisuh/hotdeal-scrap/hotdeal.db
HOTDEAL_ENV_PATH=/home/luisuh/hotdeal-scrap/.env
```

### 실행 명령어
```bash
# 웹 대시보드 실행 (포트 8000)
python3 -m uvicorn had_backend.app:app --host 0.0.0.0 --port 8000 --log-level info

# 브랜드커넥터 링크 발급 (단일 딜)
python3 brandconnect_issue_links.py --deal-id 113258

# 브랜드커넥터 링크 발급 (배치)
python3 brandconnect_issue_links.py --deal-id 113178-113200
```

---

## 8. 현재 상태

### 데이터 현황 (2026-04-12 기준)
- deals: 696건 (네이버 딜 60건, out_links 보유 57건)
- presets: 1개 (활성 1개: hotdeal.zip)
- targets: 0개
- jobs: 16건
- logs: 98건

### 운영 중 서비스
- 웹 대시보드: http://<서버IP>:8000/
- 브랜드커넥터 모니터링: http://<서버IP>:8000/brandconnect

### 브랜치 상태
- 현재 브랜치: `codex/aafa`
- 워킹트리:dirty (미커밋 변경 있음)

---

## 9. TODO (우선순위 순)

1. **✅ 브랜드커넥터 링크 발급 로직 변경 (완료)**
   - [x] `brandconnect_issue_links.py` 새 파이프라인 구현
   - [x] 백데이터 확보 후 제휴/비제휴 분류 로직 개선
   - [x] handover.md 로직 설명 업데이트

2. **✅ site 값 클렌징 + 홍보글 OmniRoute 전환 (완료 - 2026-04-19)**
   - [x] `_clean_site()` 함수로 `\xa0` 및 네이버 변형 정규화
   - [x] NVIDIA Kimi → OmniRoute `plan` 모델 전환
   - [x] E2E 파이프라인 검증 완료

3. **✅ 꿀팁 스크래핑 스크립트 생성 (완료 - 2026-04-19)**
   - [x] `todayhumor_tip_scraper.py` 신규 생성 (검색 기반 단순화)
   - [x] `todayhumor_tips` DB 테이블 + 저장 테스트

4. **홍보글 + 꿀팁 자동 게시 (다음 우선순위)**
   - [ ] 작업대기열 "승인 및 실행" → 실제 카페/소셜 자동 게시 연결
   - [ ] 승인 시 brand_connector_link + promo_text 조합하여 게시글 생성
   - [ ] 꿀팁(todayhumor_tips)도 게시판 자동 업로드에 활용

5. **카페 자동화**
   - [ ] iwacha (29643456) 댓글 자동화 안정화
   - [ ] 출석체크 automation 연결

6. **모니터링/알림**
   - [ ] 작업 실패 시 텔레그램 알림
   - [ ] 일일 실행 리포트 자동 생성

---

## 10. 참고 문서

- workflow.md: 워크플로우 정의
- AGENTS.md: AI 에이전트 협업 규칙
- docs/campingfirst_mvp_spec_20260331.md: 카페 MVP 사양

---

## 11. 최근 작업 내역 요약

### 2026-04-20 (사이트 분석 엔진 개발 + 로그인 자동화 + 네이버 카페 템플릿)

**작업 요약**
- 사이트 분석 엔진 `site_analyzer.py` 신규 개발
- 로그인 자동화 기능 추가 (LoginAutomation 클래스)
- 네이버 카페 글쓰기 템플릿 `naver_cafe_template.py` 개발
- 스마트에디터 iframe 직접 클릭 방식 구현

**구현 기능**
1. **사이트 분석 (`SiteAnalyzer`)**
   - Playwright로 페이지 로드 및 DOM 분석
   - 제목, 본문, 이미지 업로드, 제출 버튼 자동 탐지
   - iframe 프레임 분석 지원

2. **로그인 자동화 (`LoginAutomation`)**
   - 로그인 페이지 분석
   - 자동 로그인 수행
   - 세션 저장/로드 (쿠키 기반)

3. **네이버 카페 템플릿 (`NaverCafeWriter`)**
   - 카페 ID, 메뉴 ID를 파라미터로 받는 유연한 구조
   - 제목, 본문, 태그, 이미지 입력 지원
   - 스마트에디터 iframe 직접 클릭 방식
   - CLI 인터페이스 제공

**테스트 결과**
- 네이버 카페 글쓰기: 제목, 본문, 태그 정상 입력 ✅
- 스마트에디터 iframe 처리: 직접 클릭 방식 성공 ✅
- 세션 기반 로그인 유지: 성공 ✅

**사용법**
```bash
# 네이버 카페 글쓰기
python naver_cafe_template.py \
  --cafe-id 31290275 \
  --menu-id 1 \
  --title "게시글 제목" \
  --content "본문 내용" \
  --tags 태그1 태그2
```

**다음 작업**
- [ ] 대시보드 UI 통합 (상품 선택 + 타겟 사이트 선택)
- [ ] 실제 게시 버튼 클릭 기능 추가
- [ ] 이미지 업로드 기능 테스트

**구현 기능**
1. **사이트 분석 (`SiteAnalyzer`)**
   - Playwright로 페이지 로드 및 DOM 분석
   - 제목, 본문, 이미지 업로드, 제출 버튼 자동 탐지
   - iframe 프레임 분석 지원
   - 로그인 필요 여부 자동 감지
   - 스크린샷 저장 (비전 분석용)

2. **로그인 자동화 (`LoginAutomation`)**
   - 로그인 페이지 분석 (사용자명/비밀번호 필드 탐지)
   - 자동 로그인 수행
   - 세션 저장/로드 (쿠키 기반)
   - 세션 유효성 테스트

3. **자동 게시 (`AutoPublisher`)**
   - 저장된 JSON 설정 기반 자동 입력/게시
   - contenteditable div 지원
   - 이미지 업로드 지원

4. **CLI 인터페이스**
   - `python site_analyzer.py analyze <url>` - 사이트 분석
   - `python site_analyzer.py login-analyze <url>` - 로그인 페이지 분석
   - `python site_analyzer.py login <url> --username <id> --password <pw>` - 자동 로그인
   - `python site_analyzer.py session-test <site> <url>` - 세션 테스트
   - `python site_analyzer.py list` - 저장된 설정 목록
   - `python site_analyzer.py sessions` - 저장된 세션 목록

**테스트 결과**
- httpbin.org/forms/post: 3개 요소 감지 ✅
- 네이버 로그인: 사용자명/비밀번호 필드 정확히 감지 ✅
- 구글 로그인: 사용자명/비밀번호 필드 감지 ✅
- 설정 저장/로드 정상 작동 ✅

**다음 작업**
- [ ] 대시보드 UI 통합 (상품 선택 + 타겟 사이트 선택)
- [ ] 실제 비전 분석 기능 구현 (vision_analyze() 연동)
- [ ] CAPTCHA 처리 기능 추가
- [ ] 소셜 로그인 자동화

### 2026-04-19 (site 클렌징 + 홍보글 생성 OmniRoute 전환 + E2E 검증)

**작업 요약**
- 전체 자동화 파이프라인 E2E 검증 수행 (수집→상세→분류→링크생성→홍보글생성)
- 브라우저에서 대시보드 직접 접속하여 "즉시 실행" 테스트

**버그 수정: site 값 `\xa0` 클렌징**
- 원인: hotdeal.zip API가 `네이버\xa0` (non-breaking space) 반환 → SQL 필터 `site IN ('네이버','네이버쇼핑')` 누락
- 영향: ID 128210(웅진 애사비소다, 제휴 naver_me)이 대시보드에 미노출
- 수정: `fetch_hotdeal_list.py`에 `_clean_site()` 함수 추가
  - `\xa0` 제거, 공백 트림
  - `네이버쇼핑`, `멤버십` 포함 → `네이버쇼핑`
  - `네이버` 포함 → `네이버`
- DB 즉시 수정: 3건 정리 (ID 128210, 128219, 128542)

**홍보글 생성: NVIDIA Kimi → OmniRoute `plan` 모델**
- 기존: `NVIDIA_API_KEY` + `moonshotai/kimi-k2.5` (curl 기반)
- 변경: `http://192.168.50.110:20128/v1/chat/completions` + `plan` 모델 (OmniRoute 프록시)
- `free-stack` 모델 시도했으나 "all upstream accounts inactive" → `plan`으로 폴백
- 환경변수: `OMNIRITE_URL`, `PROMO_MODEL`로 오버라이드 가능
- 검증: "미니스트릿 레터링 오버핏 라운드 반팔 티셔츠" 홍보글 2건 정상 생성 확인

**변경 파일**
- `fetch_hotdeal_list.py`: `_clean_site()` 함수 추가 + `insert_rows()`에서 적용
- `had_backend/actions/hotdeal_actions.py`: `generate_promo_text()` NVIDIA → OmniRoute 전환

**검증 결과**
- py_compile: 정상
- `_clean_site()` 테스트: 5개 케이스 통과
- free-stack API: 할당량 소진 (ALL_ACCOUNTS_INACTIVE)
- plan API: 정상 응답 (한국어 홍보글 생성)
- 전체 파이프라인 E2E: 133건 수집, 2건 홍보글 생성 완료, 작업대기열 정상 표시

**꿀팁 스크래핑 스크립트 신규 생성**
- 기존 `todayhumor_dryrun.py`: 30개 게시판 자동발견 + 30개 키워드 매칭 + 점수 계산 — 복잡하고 홍보/이벤트/질문형 필터링 약함
- 새 `todayhumor_tip_scraper.py` 생성 (단순화):
  - `꿀팁` 키워드로 todayhumor 전체 검색 (`search_table_name=total`)
  - `parse_list_items()` 기존 파서 재활용
  - DB: `todayhumor_tips` 테이블 (별도 분리, url 기준 upsert)
  - `--fetch-details` 옵션으로 본문 상세 수집 가능
- 검증: 3페이지 90건 수집, 전부 제목에 "꿀팁" 명확 포함, 홍보/이벤트 필터링 불필요
- DB 저장 테스트 완료

---

### 2026-04-15 (DB 초기화 범위 조정 + 다음 링크 생성 검증 준비)

**작업 요약**
- 사용자 요청으로 테스트용 초기화를 수행했으나, 최초에 DB 전체 테이블 데이터가 삭제됨.
- 즉시 사용자 피드백 반영하여 기본 프리셋(`hotdeal.zip`) 1건 복구 완료.
- 현재 의도된 상태는 "상품/작업 데이터는 비움, 기본 프리셋은 유지".

**현재 DB 상태 (검증 결과)**
- `presets`: 2 (둘 다 `hotdeal.zip`, 활성화)
  - id=1, target_url=`https://hotdeal.zip`
  - id=2, target_url=`https://hotdeal.zip/api/deals.php`
- `deals`: 0
- `jobs`: 0
- `logs`: 0
- `targets`: 0
- `comment_pool`: 0

**백업 파일**
- 전체 삭제 직전 백업 생성됨:
  - `/home/luisuh/hotdeal-scrap/hotdeal.db.bak.fullwipe.20260415_165211`

**다음 작업 메모 (사용자 요청)**
- 다음 세션/다음 단계에서 링크 생성 검증을 다시 진행할 예정.
- 검증 시 체크 포인트:
  1) 수집 직후 `is_affiliate_candidate`/`affiliate_url_type` 즉시 반영 여부
  2) `generate-links` 호출 시 비제휴 건 skipped 처리 + reason 노출 여부
  3) `brandconnect` 도메인에서 `/affiliate(/s)` 미포함 URL 비제휴 처리 여부

---

### 2026-04-15 (HAD 대시보드/링크 생성 안정화 + URL 타입 기반 차단 고도화)

**변경 파일**
- `had_backend/app.py`
- `had_backend/static/index.html`
- `tests/test_had_backend_app.py`
- `handover.md`

**반영 내용**
- `/api/v1/naver/generate-links` 선행 검증(preflight classify) 강화
  - `_classify_url_for_link_generation(conn, deal_id)` 추가
  - 분류 우선순위 고정: `out_links_json` → `canonical_product_url` → `post_url`
  - 지원 패턴: `brandconnect(affiliate/affiliates)`, `naver.me`, `m.smartstore`, `smartstore`, `m.brand`, `brand`, `shopping`, `shoppinglive`
- 비제휴/미분류(`cls != 1`)는 발급 큐 진입 차단
  - `brand_connector_status='failed'`
  - `brand_connector_error='비제휴/미분류 URL (type=...)'`
  - `brand_connector_link=NULL`로 정리(오염 링크 제거)
  - API 응답에 `skipped` 목록 포함
- 제휴 후보(`cls == 1`)만 `processing` 전환 후 발급 프로세스 실행
- 오래된 `processing` 자동 실패 전환 유지
  - `BRANDCONNECT_PROCESSING_TIMEOUT_SEC`(기본 600초)
- 대시보드 선택 상태 안정화
  - 주기 refresh 시 선택 Set 강제 clear 제거
  - `generateLinks()`에서 DOM 체크박스 우선으로 `deal_ids` 산출 후 Set 동기화
- `/api/v1/naver/deals` 응답에 `brand_connector_error` 필드 누락 버그 수정
- 분류 로직 단일화(중복 제거)
  - 신규: `had_backend/affiliate_classifier.py`
  - 적용 경로 통합: `had_backend/app.py`, `had_backend/actions/hotdeal_actions.py`, `brandconnect_issue_links.py`, `enrich_hotdeal_details.py`
  - 규칙 고정: `brandconnect.naver.com`은 `/affiliate/` 또는 `/affiliates/`가 없으면 `brandconnect_non_affiliate`로 분류
  - 회귀 테스트 추가:
    - `tests/test_had_backend_app.py::test_generate_links_skips_brandconnect_without_affiliate_path`
    - `tests/test_brandconnect_issue_links.py::test_shared_classifier_single_source_of_truth`

**핵심 이슈 해결 결과 (사용자 리포트 2건)**
- Deal `126601`
  - 기존: unknown/오분류
  - 수정 후: `is_affiliate_candidate=0`, `affiliate_url_type=smartstore`, 발급 차단
- Deal `126610`
  - 기존: 비제휴인데도 발급 진행되어 오링크 저장 가능
  - 수정 후: `is_affiliate_candidate=0`, `affiliate_url_type=m_smartstore`, 발급 차단

**검증 결과**
- 회귀 테스트:
  - `python -m pytest -q tests/test_had_backend_app.py tests/test_brandconnect_issue_links.py tests/test_hotdeal_actions_classification.py`
  - `44 passed`
- 수집 직후 자동 분류 검증(저장 단계):
  - `save_deals_to_db()`에서 네이버 딜 저장 시 즉시 `is_affiliate_candidate`/`affiliate_url_type` 갱신 확인
  - 임시 deal_id `990001` 생성 후 `smartstore`로 즉시 비제휴(0) 반영 확인, 검증 후 삭제
- 실서버 재시작 및 API 확인:
  - 실행 프로세스: `proc_1654614b7899` (running)
  - `/api/v1/stats` 200 OK
  - `/api/v1/naver/deals` 200 OK, `brand_connector_error` 포함 확인
  - `/api/v1/naver/generate-links`에 `[126601,126610]` 전달 시
    - `deal_ids=[]`
    - `skipped`에 2건 모두 비제휴 사유 포함

**운영 메모**
- SYSTEM watch 알림은 종료된 과거 프로세스의 잔여 로그가 섞일 수 있음.
- 실제 상태 판단은 `process list` 기준으로 `running` 세션 ID를 우선 확인.

---

### 2026-04-12 (브랜드커넥터 링크 발급 로직 변경 + 백데이터 분석)

**변경 파일**
- `brandconnect_issue_links.py` (핵심 로직 변경 + 분류 함수 6개 추가)
- `had_backend/actions/hotdeal_actions.py` (`_classify_naver_url` 동기화)
- `tests/test_brandconnect_issue_links.py` (신규 테스트 15건 추가)
- `handover.md` (TODO + 작업내역 업데이트)

**변경된 파이프라인 (사용자 요청 반영)**
기존: title로 브랜드커넥터 검색 → 링크 발급
변경:
  1) `out_links_json`에서 구매링크 추출
  2) 링크 타입으로 제휴/비제휴 구별
     - 제휴: `naver.me` (리다이렉트), `brandconnect.naver.com/*/affiliate/*` (이미 BC 링크)
     - 비제휴: `smartstore`, `m.smartstore`, `brand.naver.com`, `m.brand.naver.com`, `shopping.naver.com`
  3) BC 링크면 그대로 저장 (추가 작업 불필요)
  4) naver.me면 urllib로 접속 → og:title에서 실제 상품명 재수집
  5) 재수집된 상품명으로 브랜드커넥터 검색 → 링크 발급

**신규 함수 (brandconnect_issue_links.py)**
- `classify_link(url)`: URL → (is_affiliate_candidate, url_type) 분류
- `_extract_product_name_from_html(html)`: HTML에서 og:title로 상품명 추출
- `fetch_real_product_info(url)`: naver.me URL에 접속 → (상품명, 최종 URL) 반환
- `parse_out_links(json_str)`: out_links_json 파싱
- `find_affiliate_link(out_links)`: 제휴 링크 찾아서 상품명 수집 (brandconnect은 직접 반환)
- `classify_all_links(out_links)`: 전체 링크 분류 (제휴 > 비제휴 우선)

**기존 함수 변경**
- `load_targets()`: 4-tuple → 5-tuple (out_links_json 추가)
- `load_target_by_ids()`: 동일하게 5-tuple
- `main()`: out_links_json 기반 새 파이프라인 적용 (brandconnect 링크는 즉시 저장)
- `ensure_columns()`: out_links_json 컬럼 추가
- `_classify_naver_url()` (hotdeal_actions.py): m.smartstore, m.brand 패턴 추가

**백데이터 수집/분석 결과**
- hotdeal.zip에서 29페이지(580건) 추가 수집 → DB 전체 696건, 네이버 딜 60건
- 네이버 딜 60건 out_links enrichment 완료
- 분류 결과: 제휴 2건(3.3%), 비제휴 55건(91.7%), no_links 3건
- 발견된 도메인: brand.naver.com(24), smartstore(23), m.smartstore(4), shopping(3), naver.me(2), m.brand(1)
- 분류 규칙 확정: naver.me/brandconnect(*/affiliate/*)=제휴, 나머지 직접 스토어=비제휴

**신규 테스트 (15건)**
- test_classify_link_* (10건): naver_me, smartstore, brand_store, shopping, brandconnect, brandconnect_affiliate_products, mobile_smartstore, mobile_brand_store, unknown, empty
- test_parse_out_links_* (2건): valid, empty
- test_classify_all_links_* (3건): affiliate_first, all_non_affiliate, empty
- test_extract_product_name_from_html_* (3건): og_title, title_tag, none
- test_fetch_real_product_info_* (2건): success(mock), failure(mock)

**검증 결과**
- `py_compile` 3개 파일 모두 컴파일 성공
- `python -m pytest tests/ -q` → `64 passed`

**알림: 추가 제휴 키워드**
- 사용자가 제휴 URL에 "affiliate" 외 추가 키워드가 있다고 언급하나 미기억
- 현재 백데이터(60건)에서는 naver.me, brandconnect(*/affiliate/*) 외 제외 패턴 미발견
- 향후 brandconnect 제휴 링크가 더 모이면 패턴 추가 발견 가능

---

### 2026-04-07 (DB 보안 강화 및 에러 핸들링 개선 완료)

**변경 파일**
- `migrations/001_add_constraints_and_indexes.py` (실행)
- `had_backend/actions/hotdeal_actions.py`
- `had_backend/actions/pipeline.py`
- `had_backend/app.py`

**반영 내용**
- Migration 001 실행: 9개 인덱스 생성 (deals.site, deals.bc_status, deals.fetched_at, jobs.status, jobs.type, jobs.target_id, jobs.preset_id, presets.is_active, targets.is_active)
- `hotdeal_actions.py` `get_conn()`에 `PRAGMA foreign_keys = ON`, `PRAGMA busy_timeout = 5000` 추가
- `hotdeal_actions.py` 전 함수에 try-except 블록 및 `logging` 모듈 연동:
  - `fetch_latest_deals`: URLError, TimeoutError, JSONDecodeError 처리
  - `save_deals_to_db`: 개별 딜 저장 실패 시 격리, 전체 DB 오류 시 RuntimeError raise
  - `_fetch_html`: 타임아웃 30초 추가, URLError 처리
  - `enrich_deal`: seo_url null 체크, ValueError/RuntimeError/SQLiteError 분리 처리
  - `generate_promo_text`: curl 반환값 체크, JSON 파싱 오류, API 응답 구조 이상 처리
- `pipeline.py` `log_message()`에 Python logging 연동 추가 (DB 로그 + 파일 로그 이중 기록)
- `app.py` `process_approved_jobs` 중첩 커넥션 안티패턴 제거 (단일 트랜잭션으로 통합)

**검증 결과**
- `python -m pytest tests/ -q` → `41 passed`
- `py_compile` 3개 파일 모두 컴파일 성공

### 2026-04-07 (브랜드커넥터 상태/대시보드 표시 보강 완료)

**변경 파일**
- `had_backend/app.py`
- `had_backend/static/index.html`
- `tests/test_had_backend_app.py`

**반영 내용**
- BrandConnect 대기 상태를 `pending`/`NULL` 모두 일관되게 집계/필터링하도록 수정
- 링크 생성/재시도 시 기존 브랜드커넥터 링크를 비우고 `pending`으로 전환
- 메인 대시보드 네이버 딜 목록의 대기 상태 색상을 노란색으로 표시하도록 개선
- 회귀 테스트로 pending 집계, pending 필터, 링크 초기화 동작을 검증

**검증 결과**
- `python -m pytest -q` → `41 passed`

### 2026-04-07 (문서 기반 안정화 작업 완료)

**변경 파일**
- `had_backend/app.py`
- `had_backend/static/index.html`
- `had_backend/static/brandconnect.html`
- `had_backend/static/shared.js` (신규)
- `tests/test_had_backend_app.py` (신규)
- `tests/test_brandconnect_issue_links.py`

**반영 내용**
- 정적 HTML 서빙 경로를 프로젝트 상대경로로 통일하고 `/static/shared.js` 정적 라우트 추가
- 대시보드 API 입력 검증/에러 응답(JSON) 강화 (`target_url`, `page`, `page_size`, `deal_ids`, `job_ids` 등)
- SQLite 연결 시 `foreign_keys`, `busy_timeout` 설정 및 빈번한 조회용 인덱스 자동 보장
- 메인 대시보드 로그 렌더링을 실제 `/api/v1/logs` 응답 스키마(`level/message/details/created_at`)에 맞게 수정
- 메인/브랜드커넥터 페이지의 중복 BrandConnect stats 호출 로직을 `shared.js`로 공통화
- 메인 대시보드와 브랜드커넥터 페이지의 API 실패 시 가시적인 에러 처리/토스트 개선
- 브랜드커넥터 재시도 버튼의 취약한 `event` 의존 제거
- BrandConnect 회귀 테스트를 현재 의도(네트워크 우선, 클립보드 fallback) 기준으로 갱신

**검증 결과**
- `python -m pytest tests/test_had_backend_app.py tests/test_brandconnect_issue_links.py -q` → `10 passed`
- 수동 QA:
  - `/api/v1/stats` 정상 응답 확인
  - `/api/v1/brandconnect/stats` 정상 응답 확인
  - `/api/v1/logs` 실제 로그 스키마 응답 확인
  - `/api/v1/brandconnect/retry/1` 재시도 응답 확인
  - `/api/v1/naver/deals?page=1&page_size=10` 정상 응답 확인
  - `/` 및 `/static/shared.js` HTTP 200 확인

**비고**
- Python LSP(`basedpyright`)가 현재 환경에 설치되어 있지 않아 `lsp_diagnostics`는 실행 불가. 대신 `py_compile`, pytest, TestClient 기반 수동 QA로 검증함.

### 2026-04-07 (대시보드 개발 완료)

**1) 네이버 스토어 딜 조회 섹션 추가 (메인 대시보드에 통합)**
- 변경 파일: had_backend/app.py (신규 API), had_backend/static/index.html (개선)
- 구현: 메인 대시보드에 네이버 스토어 딜 조회 섹션 통합
- API 엔드포인트:
  - `GET /api/v1/naver/deals?page=1&page_size=10` - 네이버/네이버쇼핑 딜 조회 (페이지네이션)
  - `POST /api/v1/naver/generate-links` - 선택 딜의 브랜드커넥터 링크 생성 요청
- 기능:
  - 초기 10개만 표시, "더 보기" 클릭 시 추가 로드 (무한 스크롤)
  - 체크박스 개별 선택 및 전체 선택 토글
  - "링크 생성" 버튼 클릭 시 선택한 딜들의 brand_connector_status를 'pending'으로 업데이트
  - 상태 표시 (대기/성공/실패) 및 링크 직접 표시
  - 기존 hotdeal.zip 활성화/비활성화 토글 유지

### 2026-04-07 (본 분석 결과 반영)

**프로젝트 아키텍처 분석 및 문서화**
- 변경 파일: handover.md (본 문서), evaluation.md (신규)
- 목적: 프로젝트 인계 및 아키텍처 평가 문서화

**분석 내용**:
- 백엔드 아키텍처: Starlette 기반 API 서버, 16개 엔드포인트
- 프론트엔드: Tailwind CSS 기반 반응형 UI, 2개 페이지
- 데이터베이스: SQLite 5개 테이블 (deals, presets, targets, jobs, logs)
- 핵심 스크립트 6개 분석 완료
- 브랜드커넥터: Playwright 기반 자동화, 954줄 스크립트

---

### 2026-04-06

**0-2) 브랜드커넥터 클립보드 중복 링크 문제 수정**
- 변경 파일: brandconnect_issue_links.py
- 원인: 클립보드 우선순위 1로 설정되어 이전 링크 재사용 (22건 배치 시 16건 중복)
- 구현: 클립보드 초기화 로직 추가, 우선순위 변경

**0-1) 대시보드 메인 UI 보강 - 브랜드커넥터 통계 카드**
- 변경 파일: had_backend/static/index.html
- 구현: 상단 통계에 5번째 카드 추가, fetchBCStats() 함수

**0) 브랜드커넥터 대시보드 페이지 추가**
- 변경 파일: had_backend/static/brandconnect.html (신규), had_backend/app.py
- 구현: /brandconnect 페이지, 통계/목록/재시도 기능

---

### 2026-04-07

**1) 캠핑퍼스트 승인 기반 댓글 자동화 웹 UI 및 API 개발**
- 변경 파일: 
  - `had_backend/static/approve.html` (신규)
  - `had_backend/app.py`
- 구현 내용:
  - 작업 승인 전용 웹 UI 페이지 생성 (`/approve`)
  - 대기 중인 작업(PENDING) 목록 조회 및 승인/거부 버튼
  - 승인된 작업(APPROVED) 목록 조회
  - `/api/v1/jobs/process-approved` POST 엔드포인트 추가
  - 승인된 작업을 COMPLETED로 변경하는 기본 처리 로직
  - 30초 자동 새로고침 기능
- 접속: `http://192.168.50.179:8000/approve`
- 참고: PLAN.md에 전체 작업 계획 문서화 (작업 1: 세션 만료 해결은 미완)

---

### 2026-04-04

**1) brandconnect_issue_links.py 배치 자동화 구현**
- 변경 파일: brandconnect_issue_links.py, hotdeal.db
- 구현: --deal-id 확장, retry_count, last_attempt 컬럼, 지수 백오프

---

### 이전 작업 (handover.md 기존 참조)

0) Naver BrandConnect 실발급 자동화(세션 재사용) 구현
1) Naver 브랜드 커넥터 링크 생성 로직 추가
2) TodayHumor 꿀팁 필터 품질 개선
3) TodayHumor 상세 수집 제어 기능 추가
4) TodayHumor SQLite 저장 기능 추가
5) Groq 테스트 스크립트 curl 방식으로 통일
6) LLM 헬퍼 스크립트/환경 예시 복구 및 정리
7) 프로젝트 상대경로 기반 env/db 사용으로 통일
8) 캠핑퍼스트 MVP → iwacha 전환 및 댓글/출석 자동화 안정화
9) 활성 타겟 일괄 큐잉 웹 API 추가

---

### 2026-04-10 (브랜드커넥터 로그인 세션 확보 도구 추가)

**변경 파일**
- `scripts/brandconnect_session_bootstrap.py` (신규)

**반영 내용**
- 기존 storage_state로 인증 여부 확인 후, 미인증 시 자동/수동 로그인 대기
- 로그인 성공 시 storage_state 파일 갱신

**검증 결과**
- headless 세션 갱신 시도 → brandconnect 접속 타임아웃 (네트워크/접속 이슈 가능)

---

### 2026-04-10 (브랜드커넥터 stealth/채널 옵션 추가)

**변경 파일**
- `brandconnect_issue_links.py`
- `had_backend/app.py`
- `scripts/brandconnect_session_bootstrap.py`

**반영 내용**
- `--browser-channel`, `--stealth`, `--user-agent` 옵션 추가
- 환경변수로 동일 옵션 설정 가능 (`BRANDCONNECT_BROWSER_CHANNEL`, `BRANDCONNECT_STEALTH`, `BRANDCONNECT_USER_AGENT`)
- 대시보드 링크 생성 프로세스가 위 옵션을 전달하도록 업데이트

**검증 결과**
- `python3 -m py_compile` 컴파일 성공
- `python3 brandconnect_issue_links.py --deal-id 123959 --headless --stealth --browser-channel chrome` → ERR_CONNECTION_RESET 지속

---

### 2026-04-10 (undetected-chromedriver 러너 추가)

**변경 파일**
- `brandconnect_issue_links_uc.py` (신규)
- `had_backend/app.py`

**반영 내용**
- undetected-chromedriver 기반 링크 발급 러너 추가
- `BRANDCONNECT_RUNNER=undetected` 시 새 러너 사용
- `BRANDCONNECT_UC_COOKIES_PATH`, `BRANDCONNECT_UC_CHROME_MAJOR`, `BRANDCONNECT_USER_AGENT` 지원
- undetected 실행 시 `.venv/bin/python` 자동 사용

**검증 결과**
- venv 생성 및 undetected-chromedriver/selenium 설치
- Chrome 146에 맞춰 `--chrome-major 146`로 실행
- `brandconnect_issue_links_uc.py --deal-id 123959 --headless --chrome-major 146` → ERR_CONNECTION_RESET 지속

---

### 2026-04-10 (undetected 러너 proxy/headless 옵션 추가)

**변경 파일**
- `brandconnect_issue_links_uc.py`
- `had_backend/app.py`

**반영 내용**
- undetected 러너에 `--proxy` 추가 (환경변수 `BRANDCONNECT_PROXY`)
- 대시보드 실행 시 `BRANDCONNECT_HEADLESS=0`이면 headless 비활성화
- `BRANDCONNECT_PROXY` 설정 시 undetected 러너에 전달

**검증 결과**
- `python3 -m py_compile` 컴파일 성공
- `brandconnect_issue_links_uc.py --deal-id 123959 --headless --chrome-major 146` → ERR_CONNECTION_RESET 지속

---

### 2026-04-10 (xvfb로 headless 해제 실행)

**변경 파일**
- `had_backend/app.py`

**반영 내용**
- `BRANDCONNECT_USE_XVFB=1`일 때 `xvfb-run -a`로 백그라운드 실행
- `BRANDCONNECT_HEADLESS=0`이면 headless 옵션 제거

**검증 결과**
- 브랜드커넥터 실행 시 xvfb-run으로 프로세스 생성 확인
- `net::ERR_CONNECTION_RESET` 지속, 일부 항목 `Event loop is closed` 발생

---

### 2026-04-10 (로컬 실행 결과 서버 반영 경로 추가)

**변경 파일**
- `brandconnect_issue_links_uc.py`
- `scripts/brandconnect_import_results.py` (신규)

**반영 내용**
- undetected 러너에서 `--result-json`으로 실행 결과 파일 출력 지원
- 서버에서 결과 JSON을 DB에 반영하는 import 스크립트 추가

**검증 결과**
- `python3 -m py_compile brandconnect_issue_links_uc.py scripts/brandconnect_import_results.py` 성공

---

### 2026-04-10 (undetected 결과 JSON 생성 및 DB 반영 실행)

**실행 명령**
- `.venv/bin/python brandconnect_issue_links_uc.py --deal-id 123959,123961,123917,123921,123925,123502,123439,123423,123342 --chrome-major 146 --result-json .debug/brandconnect/local-results.json`
- `python3 scripts/brandconnect_import_results.py --input .debug/brandconnect/local-results.json`

**결과 요약**
- 결과 JSON 생성 완료 (`.debug/brandconnect/local-results.json`)
- 9건 DB 반영 완료
- brandconnect stats: success=0, failed=9

---

### 2026-04-10 (작업 정리: 진행/구현/실패)

**진행한 것**
- 브랜드커넥터 로그인 페이지/구글 로그인 페이지 접속 비교 테스트 수행
- Playwright 브라우저에서 사용자 수동 로그인 후 storage_state 재저장
- 대시보드 API(`/api/v1/naver/generate-links`)로 재시도 반복 실행 및 로그/통계 점검
- 실패 9건에 대해 실제 네이버 상품 URL 재추출(게시글 URL과 구분)

**구현한 것**
- `had_backend/app.py`
  - `BRANDCONNECT_HEADLESS`로 headless on/off 제어
  - `BRANDCONNECT_USE_XVFB=1` 시 `xvfb-run -a`로 백그라운드(headful hidden) 실행
  - `BRANDCONNECT_RUNNER=undetected` 분기 및 uc 전용 인자 전달
- `brandconnect_issue_links.py`
  - `--browser-channel`, `--stealth`, `--user-agent` 옵션 추가
- `brandconnect_issue_links_uc.py` (신규)
  - undetected-chromedriver 기반 발급 러너 구현
  - `--chrome-major`, `--proxy`, `--result-json` 옵션 지원
- `scripts/brandconnect_session_bootstrap.py` (신규)
  - 수동 로그인 세션 확보/갱신 도구
- `scripts/brandconnect_import_results.py` (신규)
  - 로컬 실행 결과 JSON을 서버 DB에 반영하는 import 도구

**실패/이슈 정리**
- 서버 자동화 실행(Playwright/undetected 모두)에서 `net::ERR_CONNECTION_RESET` 지속 발생
- headless 해제 + xvfb 백그라운드 실행에서도 동일 증상 재현
- 일부 재시도 루프에서 `Event loop is closed` 오류 발생
- 원인 판단: 코드 옵션 전달 문제보다는 서버 런타임 네트워크/접속 환경 이슈 가능성 높음

**참고 데이터**
- 재추출된 네이버 상품 URL은 별도 응답으로 사용자에게 제공 완료
- 9건 실행 결과 파일: `.debug/brandconnect/local-results.json`

---

### 2026-04-11 (브랜드커넥터 워크플로우 전면 분석 및 재구성 시도)

**목표**: 브랜드커넥터 링크 발급 워크플로우 실패 원인 규명 및 새 방식 구현

#### 실패 원인 분석 (근본적 문제 4가지)

1. **Playwright 헤드리스 모드 → 네이버 WAF 차단**
   - `curl`/`requests`로는 brandconnect.naver.com 접속 가능
   - Playwright 헤드리스 Chromium으로는 `net::ERR_CONNECTION_RESET` 발생
   - 네이버 WAF가 헤드리스 브라우저의 TLS 지문을 탐지/차단
   - xvfb + 헤풀 모드로는 접속 성공 확인됨

2. **저장된 세션(storage_state) 서버 측 만료**
   - `.secrets/brandconnect_storage_state.json`에 쿠키 존재 (NID_SES, NID_AUT)
   - 서버 측 세션 만료 → 로그인 페이지로 리다이렉트
   - 재로그인 불가 → 전체 실패 (9건 모두 failed, 성공 0건)

3. **상품명 매칭 기준 과도 (99% 유사도)**
   - 기존: `SequenceMatcher` 99% 이상만 매칭 → 미세한 이름 차이로 실패
   - 개선: 키워드 기반 매칭 + 유사도 70%+ 기준

4. **상품 URL 추출 실패**
   - `canonical_product_url`이 hotdeal.zip 리디렉트 URL만 저장
   - 실제 네이버 상품 URL 미추출 → brandconnect 검색 불가

#### 구현 내용

1. **`brandconnect_v2.py` (신규)** — xvfb + 헤풀 Playwright 기반 링크 발급 스크립트
   - `SessionManager`: 세션 유효성 사전 검증, 만료 시 재로그인 유도
   - `LinkIssuer`: 네트워크 응답 가로채기 + DOM 링크 추출 + 클립보드 3중 폴백
   - 키워드 기반 상품 매칭 (유사도 + 키워드 겹침 점수)
   - 대시보드 연동 (app.py의 `_start_brandconnect_link_generation` 교체)

2. **`scripts/brandconnect_login_web.py` (신규)** — 웹 기반 로그인 도구
   - Xvfb + Playwright 헤풀 브라우저
   - 스크린샷 파일 기반 통신 (HTTP 서버)
   - 웹 UI에서 ID/PW 입력 → Playwright 브라우저에 자동 입력
   - 문제: 네이버 로그인 폼 동적 전환으로 인해 ID/PW 입력이 불안정

3. **DB 초기화** — 실패한 9건 딜의 brand_connector_status를 NULL로 리셋

#### 미해결 문제

- **네이버 로그인 세션 확보 불가**: Chrome으로 직접 로그인해도 brandconnect에서 세션 유지 안 됨
  - 가능한 원인: brandconnect 계정 설정, 네이버 보안 정책, Space ID 접근 권한 등
  - 추가 조사 필요: brandconnect 계정 상태, 제휴 약관 동의 여부 확인

#### 테스트 결과

- `python -m pytest tests/ -q` → 44 passed
- `brandconnect_v2.py` syntax check: OK
- xvfb + 헤풀 Playwright → brandconnect.naver.com 접속 성공
- 웹 로그인 도구 → ID/PW 입력 동작하나 로그인 최종 성공까지 미도달

#### 남겨진 파일

- `brandconnect_v2.py`: 새 링크 발급 스크립트 (세션 확보 후 사용 가능)
- `scripts/brandconnect_login_web.py`: 웹 로그인 도구 (불안정)

---

### 2026-04-12 (검색 로직 개선 + 분류 로직 연동)

**작업 목표**
- hotdeal.zip에서 실제 구매 가능한 링크만 수집
- 제휴/비제휴 분류 로직 연동
- DB 초기화 후 새로 스크래핑

**변경 파일**
- `enrich_hotdeal_details.py` (핵심 로직 변경)
- `handover.md` (작업내역 업데이트)

**변경된 검색 로직 (사용자 요구 반영)**

기존: 모든 링크 수집 (네이버페이, 캠페인, 커뮤니티 링크 포함)
변경:
  1) "구매하기" 버튼의 href만 추출 (실제 구매 링크)
  2) 리다이렉트 서비스 추적 (link.fmkorea, s.ppomppu, unsafelink)
  3) 네이버페이/캠페인/커뮤니티 링크 제외
  4) 실제 구매 가능한 네이버 쇼핑몰 링크만 저장

**수정된 함수 (enrich_hotdeal_details.py)**

1. `_extract_buy_button_link(html_text)`: "구매하기" 버튼의 href 추출
   - 패턴 1: `<a href="..." class="buy-button...">`
   - 패턴 2: `<a class="buy-button..." href="...">`

2. `_is_naver_purchase_link(url)`: 실제 구매 가능한 네이버 쇼핑몰 링크 확인
   - 구매 가능 도메인: smartstore, brand, shopping, m.smartstore, m.brand, shoppinglive
   - 구매 불가 패턴: /festa/, /event/, /promotion/, /campaign/, /benefit/, /special/, /limited/, /deal/
   - 실제 상품 패턴: /products/, /product/, /item/, /detail/

3. `_resolve_redirect_url(url)`: 리다이렉트 서비스에서 실제 대상 URL 추출
   - link.fmkorea.org/link.php?url=... → URL 디코딩
   - s.ppomppu.co.kr?target=... → base64 디코딩
   - unsafelink.com/https://... → 내부 URL 추출
   - quasarzone.com?url=... → URL 디코딩

4. `parse_page(html_text)`: 상세 페이지에서 필요한 데이터 추출
   - 반환값 변경: (price_table, price_summary, details_text_raw, details_text_clean, details_images, out_links)
   - → (price_summary, description_text, details_images, out_links)
   - "구매하기" 버튼 링크만 out_links에 저장

5. `ensure_columns(cur)`: DB 컬럼 구조 변경
   - 제거: price_table_json, details_text_raw, details_text_clean, naver_brand_connector_links_json
   - 추가: description_text, is_affiliate_candidate, affiliate_url_type

6. `main()`: 분류 로직 연동
   - brandconnect_issue_links.py의 classify_link 함수 import
   - 구매 링크 분류 후 is_affiliate_candidate, affiliate_url_type 저장

**분류 로직 연동**

- brandconnect_issue_links.py의 classify_link 함수 import
- 분류 규칙:
  - 제휴(1): brandconnect.naver.com/*/affiliate/*, naver.me
  - 비제휴(0): smartstore, brand, shopping, m.smartstore, m.brand, shoppinglive
  - 미분류(NULL): unknown

**수집 결과**

1. hotdeal.zip 추가 수집:
   - 30~40페이지: 127건 신규 추가
   - 41~50페이지: 157건 신규 추가
   - 51~70페이지: 348건 신규 추가

2. DB 초기화 후 새로 스크래핑:
   - 전체 딜: 1000건
   - 네이버/네이버쇼핑 딜: 110건 (11.0%)

3. 분류 결과:
   - 구매 링크 있는 딜: 110건 (100%)
   - 제휴 링크: 4건 (3.6%)
   - 비제휴 링크: 105건 (95.5%)
   - 미분류: 1건 (0.9%)

4. 분류 타입 분포:
   - brand_store (brand.naver.com): 다수
   - smartstore (smartstore.naver.com): 다수
   - m_brand_store (m.brand.naver.com): 일부
   - naver_me (naver.me): 4건 (제휴)

**검증 결과**
- py_compile: 정상
- enrich_hotdeal_details.py 실행: 110건 모두 처리 성공
- 분류 로직 정상 동작 확인

**다음 작업 (TODO)**
1. 더 많은 페이지 수집 (71페이지~) - 네이버 딜 비율 높이기
2. 제휴 링크 활용 - 브랜드커넥터 링크 발급
3. 홍보 멘트 생성 - price_summary 활용
4. 소셜 카페 자동 홍보 - LLM 처리 없이 원본 데이터 사용
- 기존 `brandconnect_issue_links.py`: 미삭제 (참고용 보존)
