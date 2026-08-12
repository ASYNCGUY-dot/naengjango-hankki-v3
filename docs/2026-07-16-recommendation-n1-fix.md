# 추천 API N+1 쿼리 개선 작업 요약 (2026-07-16)

더블체크용 요약 문서. 작업자: Claude Code(위임 세션). 커밋: `7ecff60`
(`fix: 추천 API N+1 쿼리를 배치 조회로 개선하고 recipe_id 인덱스 추가`), 아직 `origin/master`에는
push 안 됨(로컬 커밋만 있는 상태).

## 문제

`GET /recommendation/{user_id}`([api/routers/recommendation.py](../api/routers/recommendation.py))가
실제로 15~30초 이상 걸려서, Reflex 프론트엔드(`naengjango_v2/naengjango_v2.py`의
`get_recommendations`)에서 `requests.get` timeout을 60초로 늘려야 했다.

원인은 [src/agents/recommendation_agent.py](../src/agents/recommendation_agent.py)의
`get_candidate_recipes()`와 `score_by_ingredients()`가 승인된 레시피(최대 1,148개)마다
`recipe_tags`/`recipe_ingredients`/`recipe_likes`에 개별 SELECT를 날리는 N+1 패턴이었다 -
레시피 하나당 최대 3~5개 쿼리, 총 쿼리 수가 O(레시피 수)로 늘어난다.

## 변경 내용

**건드리지 않은 것**: 랭킹 로직 자체(9차례 실측 튜닝된 정렬 key, `qualifies` 판단, 카테고리
tier, 단백질 매칭, 핵심 재료 판단 등)는 한 줄도 안 바꿨다. DB 접근 방식만 바꿨다.

1. `get_candidate_recipes()`: 레시피 목록을 먼저 다 가져온 뒤, `recipe_likes`(유저 등록 레시피만),
   `recipe_tags`(allergy, nutrition_group) 조회를 각각 `recipe_id IN (...)` 한 번씩으로 바꾸고
   결과를 딕셔너리로 인덱싱해서 루프 안에서는 조회 없이 참조만 하도록 고쳤다.
2. `score_by_ingredients()`: 후보 레시피 id를 모아 `recipe_tags`(ingredient)와
   `recipe_ingredients`를 각각 `recipe_id IN (...)` 한 번씩으로 배치 조회하도록 고쳤다.
3. `_get_weighted_recipe_ingredients()`를 조회 부분(`_get_weighted_recipe_ingredients`)과
   가중치 계산 부분(`_get_weighted_recipe_ingredients_from_rows`)으로 분리해서, 배치로
   미리 가져온 행을 재사용할 수 있게 했다. 단건 조회가 필요한 다른 호출부는 그대로 쓸 수 있다.
4. [migration/003_add_indexes.sql](../migration/003_add_indexes.sql) 신규 - `recipe_tags`,
   `recipe_ingredients`, `recipe_likes`의 `recipe_id`에 각각 btree 인덱스 추가
   (`CREATE INDEX IF NOT EXISTS`, 재실행해도 안전).

## 검증

- **정확성**: 로컬 `data/app.db`(SQLite, 승인된 레시피 1,148개)로 git 커밋 전(baseline) 파일과
  수정본을 동시에 로드해서 비교했다. user_id 1/2/5, 재료 입력 없음/7개 입력 총 6가지 조합에서
  전체 후보 리스트(최대 1,144개)의 순서와 모든 랭킹 필드(`ingredient_overlap`, `qualifies`,
  `category_tier`, `matched_weight`, `step_count`, `missing_count`, `coverage_ratio`,
  `has_protein_match`, `core_ok`)가 baseline과 완전히 동일함을 확인했다.
- **성능(로컬)**: 같은 조건에서 0.87~0.96초 -> 0.42~0.55초, 1.7~2.1배 단축. SQLite는 쿼리당
  오버헤드가 낮아서 이 수치는 보수적인 하한이다 - 실제 병목은 Postgres(Supabase)로의 네트워크
  왕복 지연이라, 쿼리 수를 O(레시피 수)에서 O(1)로 줄인 효과는 운영 환경에서 더 크게 나타날
  가능성이 높다. **운영 API(`GET /recommendation/{user_id}`)의 실제 응답 시간은 아직 재측정
  안 했다 - 확인 필요.**
- `src/agents/recommendation_agent.py`의 `__main__` 블록도 그대로 정상 실행됨을 확인했다.
- **인덱스**: 실제 운영 Supabase Postgres(`.env`의 `POSTGRES_URL`)에 마이그레이션을 실행했고,
  `pg_indexes` 조회로 `idx_recipe_tags_recipe_id`, `idx_recipe_ingredients_recipe_id`,
  `idx_recipe_likes_recipe_id` 세 인덱스가 생성됐음을 확인했다.

## 일부러 안 한 것

`get_candidate_recipes()`의 `recipe_id IN (...)`를 `recipes`와의 JOIN으로 바꾸는 리팩터는
보류했다. 지금 레시피 1,148개 규모에서는 IN 리스트 방식도 실측상 문제가 없었고, 지금 리팩터하면
코드 패턴이 갈리고(한 함수는 JOIN, 한 함수는 IN) 이미 끝낸 검증을 다시 해야 하는 비용만 먼저
진다고 판단했다. 유저 등록 재료·레시피가 늘어나는 방향성(상용화 고려)을 감안해서, 레시피 수가
유의미하게 늘어나거나 등록 기능이 실제로 열리면 다시 검토하기로 했다 - 상세 배경은
`memory/project_recommendation_agent_scaling.md`(Claude Code 메모리)에 남겨뒀다.

`recipes(status)` 인덱스도 일부러 안 넣었다 - 값 종류가 적어(대부분 'approved') 옵티마이저가
안 쓸 수 있고, `EXPLAIN ANALYZE`로 실제 쿼리 플랜을 확인 안 한 상태라 효과가 불확실해서다.

## 남은 일 / 더블체크 포인트

- [ ] 로컬 커밋(`7ecff60`)을 `origin/master`에 push할지 결정
- [ ] 운영 `GET /recommendation/{user_id}` 실제 응답 시간 재측정(개선 전 15~30초 대비 얼마나
      줄었는지 실측 필요 - 지금까지는 로컬 SQLite 수치만 확인함)
- [ ] Reflex 쪽 `requests.get` timeout(60초, `naengjango_v2/naengjango_v2.py`)을 줄여도 되는지
      재측정 후 판단
- [ ] `recipes(status)` 인덱스 필요 여부는 운영 쿼리 플랜(`EXPLAIN ANALYZE`)으로 확인 후 결정
