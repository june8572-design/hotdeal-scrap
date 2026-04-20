# Agent 협업 규칙 (hotdeal-scrap 프로젝트)

## 원칙
- 모든 AI 작업자는 이 파일을 먼저 읽고 협업 방식을 따라야 함.
- **handover.md**가 유일한 협업 문서 — 진행상황, 현재 상태, 장애, 다음 작업을 여기에 반드시 기록.
- 새로운 AI는 handover.md "최근 작업 내역 요약" 섹션부터 읽고 이어서 작업.
- Git 커밋은 가능한 경우 하지만, 항상 handover.md에 커밋 내역(또는 코드 상태) 요약을 기입.

## 문서 구조 (handover.md)
- **Goal Summary**: 프로젝트 전반 목표
- **Key Files**: 핵심 파일 경로
- **Database Schema**: DB 구조
- **Data Sources**: 외부 API/사이트
- **Scripts and What They Do**: 각 스크립트 설명
- **주의사항**: 보안/운영 원칙
- **TODO (사용자 입력 대기)**: 구체적 다음 작업 목록 (우선순위 포함)
- **최근 작업 내역 요약**: 실제 반영된 코드 작업 (커밋/파일 목록)

## 작업 절차
1. handover.md의 TODO 섹션 확인.
2. TODO가 없거나 불명확하면, 코드/DB 현황 조사 후 새로운 TODO 작성.
3. 작업 시작 전에 `## 최근 작업 내역 요약` 마지막에 새로운 항목 추가 (계획).
4. 작업 완료 후, 해당 항목을 "완료"로 업데이트하고 결과 요약.
5. 필요시 새로운 TODO 추가.

## 현재 프로젝트 개요
- 핵심: hotdeal.zip 크롤링 → 네이버/네이버쇼핑 상품 상세 수집 → 브랜드커넥터 링크 생성 → 프라툼 글 생성 → Groq 요약
- 웹 대시보드: `had_backend/app.py` (FastAPI 기반 UI + 관리)
- 파이프라인: `had_backend/actions/` 하위 액션들
- 테스트: `tests/` 디렉토리
- 데이터: `hotdeal.db` SQLite

## 보안 지침
- API 키/비밀값: `.env` 파일 환경변수만 사용. 코드 하드코딩 금지.
- 세션/쿠키: Playwright storage_state 파일 (`.secrets/`) 관리.
- 민감 정보는 handover.md에 절대 노출하지 않음.