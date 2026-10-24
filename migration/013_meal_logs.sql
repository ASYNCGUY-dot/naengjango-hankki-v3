-- 식사별 실제 섭취량과 1인분 영양 스냅샷. 자정 초기화는 날짜별 조회이며 행은 보존한다.
-- consumed_at/updated_at/deleted_at은 API가 UTC ISO 형식(소수초 6자리)으로 저장한다.
CREATE TABLE meal_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
    recipe_name TEXT NOT NULL,
    servings DOUBLE PRECISION NOT NULL CHECK (servings >= 0.1 AND servings <= 10),
    consumed_at TEXT NOT NULL,
    nutrition_snapshot_json TEXT NOT NULL,
    request_id TEXT NOT NULL,
    -- 원 요청은 수정/레시피 삭제 후에도 남겨 idempotency 키의 재사용을 판별한다.
    request_recipe_id INTEGER NOT NULL,
    request_servings DOUBLE PRECISION NOT NULL CHECK (request_servings >= 0.1 AND request_servings <= 10),
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE (user_id, request_id)
);

CREATE INDEX idx_meal_logs_user_consumed_at ON meal_logs (user_id, consumed_at)
    WHERE deleted_at IS NULL;
