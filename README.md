# 냉장고 한끼

냉장고에 있는 재료로 만들 수 있는 레시피를 추천하는 모바일 웹 앱이다.
알레르기가 있으면 그 재료가 든 메뉴를 추천에서 빼준다.

**https://naengjango-hankki-v3-web.onrender.com**

> 무료 서버라 첫 접속에 30초쯤 걸린다. 화면에 "서버를 깨우는 중"이 뜨면 기다리면 된다.

## 무엇을 하는가

공공데이터의 조리식품 레시피 **1,148개**와 식품영양성분 **30만 건**을 재료 기준으로
연결한다. 사용자가 가진 재료를 넣으면 겹치는 재료가 많은 순으로 정렬하고, 프로필의
알레르기·건강목표·조리도구를 반영해 후보를 좁힌다.

핵심은 **알레르기 제외**다. 태그가 정확히 일치할 때만 거르면 놓치는 것이 있다. 원본
공공데이터의 표기가 통일돼 있지 않아 `달걀`(200개)과 `계란`(27개)이 서로 다른 태그로
들어 있기 때문이다. 동의어를 묶어서 거른다.

## 기술

| 영역 | 스택 |
|---|---|
| 백엔드 | FastAPI, psycopg2, Supabase(Postgres) |
| 프론트 | Vite, React 19, TypeScript 6, React Router 7 |
| 테스트 | pytest 214개, Vitest 109개 |
| 배포 | Render (정적 사이트 + 웹 서비스), 무료 티어 |

API 응답 타입은 손으로 쓰지 않는다. `scripts/dump_openapi.py`가 저장소 코드에서
OpenAPI 명세를 뽑고 `openapi-typescript`가 프론트 타입을 만든다. CI가 그 둘의 어긋남을
검사하므로, 백엔드 응답 모양이 바뀌면 프론트 빌드가 먼저 깨진다.

## 구조

```
api/          FastAPI 라우터 (18개) - 얇은 HTTP 래퍼
src/agents/   도메인 로직 - 추천·인증·영양·안전 등
frontend/     React 앱
migration/    Postgres 스키마 (001~007, 순서대로 적용)
scripts/      운영 도구 (배포 점검·백업·초기화 링크)
tests/        pytest
docs/         작업 기록
```

라우터는 얇게 유지한다. 도메인 로직은 `src/agents/`에 있고 라우터는 HTTP 관심사(인가,
상태 코드, 요청 검증)만 다룬다.

## 개발

```bash
python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

```bash
./.venv/Scripts/python.exe -m pytest -q
```

```bash
cd frontend && npm ci && npm run dev
```

`.env`에 `POSTGRES_URL`이 필요하다. 필요한 환경변수 전체는 `render.yaml`에 선언돼 있고,
`tests/test_deploy_config.py`가 코드가 읽는 이름과 그 선언을 대조한다.

## 배포 점검

```bash
./.venv/Scripts/python.exe scripts/smoke_test_deploy.py
```

배포된 서비스를 실제로 태운다. CORS는 "Render 정적 사이트 → Render API"라는 경계에서만
검증되므로 로컬 테스트가 덮지 못한다. 검증 계정을 스스로 만들고 지운다.

## 문서

- [V3_HANDOFF.md](V3_HANDOFF.md) — 설계 판단과 실제로 겪은 함정. **8절을 먼저 읽을 것**
- [docs/PHASE4_지인테스트.md](docs/PHASE4_지인테스트.md) — 사용자 테스트 준비물과 분석 쿼리

## 알려진 제약

**비밀번호 초기화 메일이 나가지 않는다.** Render 무료 웹 서비스가 SMTP 포트를 막는다.
자격증명 문제가 아니라 플랫폼 제약이다(같은 코드가 로컬에서는 발송된다). 화면은 이
사실을 그대로 말하고, `scripts/make_reset_link.py`로 링크를 직접 만들어 전달한다.

**추천이 웜 상태에서 2.4초 걸린다.** 무료 티어가 0.1 CPU라 CPU 바운드 구간만 증폭된다.
같은 서버에서 검색은 0.6초다.

## 이력

V1(CLI) → V2(Reflex 단일 페이지) → V3(React). V2는 화면 전체가 하나의 라우트라 레시피
상세를 링크로 공유할 수 없었고 뒤로가기도 동작하지 않았다. V3에서 진짜 URL로 쪼갠 것이
이번 전환의 가장 실질적인 이득이다.
