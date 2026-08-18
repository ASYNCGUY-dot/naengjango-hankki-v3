-- V3 (2026-08-18): 사용 로그 - Phase 4 지인 테스트의 이탈 지점을 보기 위한 것
--
-- 배경
-- V2는 84개 기능을 만들고 단 한 명에게도 검증받지 못했다. Phase 4에서 지인 5명에게
-- 일주일 써보게 하는데, 그때 "재료 입력 수, 추천 호출 수, 이탈 지점"을 봐야 한다.
-- 그런데 지금 DB로는 답할 수 없는 게 있다.
--
--   가입      -> users.created_at (006에서 추가)                 볼 수 있다
--   온보딩    -> users.health_goal IS NOT NULL                   완료 여부만, 시점은 모른다
--   재료 입력 -> ingredients 행                                  개수만, 시점은 모른다
--   추천 호출 -> 아무 흔적도 없다                                볼 수 없다
--   상세 열람 -> 아무 흔적도 없다                                볼 수 없다
--
-- "이탈 지점"은 어디까지 갔는지가 아니라 언제 멈췄는지의 문제다. 상태만 봐서는
-- 첫날 재료를 넣고 안 돌아온 사람과 엿새째까지 쓰다 멈춘 사람이 구분되지 않는다.
-- 그래서 시각이 남지 않는 행동에 한해 이벤트를 쌓는다.
--
-- 남기지 않는 것: 화면 전환, 스크롤, 체류 시간 같은 것. 지금 필요한 판단(어느 단계에서
-- 멈추는가)에 쓰이지 않고, 무료 티어에서 쓰기 비용만 늘린다.
--
-- 사용법: 006 다음에 적용한다.

BEGIN;

CREATE TABLE IF NOT EXISTS usage_events (
    id SERIAL PRIMARY KEY,
    -- 비로그인도 레시피 상세를 볼 수 있다(공유 링크). 그 열람도 세고 싶으므로 NULL 허용.
    -- 계정을 지우면 그 사람의 로그도 함께 지운다 - 개인정보를 남겨둘 이유가 없다.
    user_id INTEGER REFERENCES users (id) ON DELETE CASCADE,
    -- 'login' | 'onboarding_done' | 'pantry_add' | 'recommend' | 'recipe_view'
    event TEXT NOT NULL,
    -- recipe_view일 때만 채운다. 어떤 레시피가 실제로 열렸는지가 다음 판단의 근거다.
    -- 레시피가 지워져도 "열람이 있었다"는 사실은 남아야 하므로 외래키를 걸지 않는다.
    recipe_id INTEGER,
    created_at TEXT NOT NULL
);

-- Phase 4에서 실제로 던질 질문은 "이 사람이 언제 무엇을 했나"다. 사람별로 시간순
-- 정렬해서 읽게 되므로 (user_id, created_at)으로 묶어 건다.
CREATE INDEX IF NOT EXISTS idx_usage_events_user_time
    ON usage_events (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_usage_events_event
    ON usage_events (event);

COMMIT;

-- 적용 후 확인용:
--   SELECT column_name FROM information_schema.columns
--    WHERE table_schema='public' AND table_name='usage_events';
--
-- Phase 4에서 이탈 지점 보는 법 (사람별로 어디까지 갔고 마지막이 언제인가):
--   SELECT u.username,
--          MIN(e.created_at) FILTER (WHERE e.event = 'onboarding_done') AS 온보딩,
--          MIN(e.created_at) FILTER (WHERE e.event = 'pantry_add')      AS 첫재료,
--          COUNT(*)          FILTER (WHERE e.event = 'recommend')       AS 추천호출,
--          COUNT(*)          FILTER (WHERE e.event = 'recipe_view')     AS 상세열람,
--          MAX(e.created_at)                                           AS 마지막활동
--     FROM users u LEFT JOIN usage_events e ON e.user_id = u.id
--    GROUP BY u.id, u.username
--    ORDER BY 마지막활동;
