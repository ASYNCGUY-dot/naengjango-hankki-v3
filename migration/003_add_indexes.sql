-- recommendation_agent.py의 N+1 쿼리를 recipe_id IN (...) 배치 조회로 바꾼 뒤에도,
-- 그 배치 조회 자체가 recipe_id로 필터링하므로 recipe_tags/recipe_ingredients/recipe_likes에
-- recipe_id 인덱스가 없으면 매번 풀스캔이 된다. IF NOT EXISTS로 재실행해도 안전하게 만든다.
--
-- 사용법: 002_migrate_data.py와 같은 방식으로 POSTGRES_URL이 가리키는 Supabase Postgres에
-- 직접 적용한다(psql이나 Supabase SQL editor에서 실행).
--
-- recipes(status) 인덱스는 일부러 넣지 않았다 - status 값의 종류가 몇 개 안 되고(대부분
-- 'approved') 실제 쿼리 플랜(EXPLAIN ANALYZE)으로 옵티마이저가 이 인덱스를 실제로 쓰는지
-- 확인 안 된 상태라, 효과가 불확실한 인덱스를 먼저 넣기보다는 확실히 병목이었던 recipe_id
-- 조회부터 반영한다.

CREATE INDEX IF NOT EXISTS idx_recipe_tags_recipe_id ON recipe_tags (recipe_id);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_recipe_id ON recipe_ingredients (recipe_id);
CREATE INDEX IF NOT EXISTS idx_recipe_likes_recipe_id ON recipe_likes (recipe_id);
