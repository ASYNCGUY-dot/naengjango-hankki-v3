-- V3 (2026-08-20): 자랑하기 - 이 서비스로 만들어본 결과를 올리고 서로 좋아요를 누른다
--
-- 배경
-- 지금까지 이 앱은 "무엇을 만들지 정하는" 데서 끝났다. 실제로 만들었는지, 어땠는지는
-- 후기 한 줄 말고는 남는 곳이 없다. 자랑하기는 그 뒤를 잇는다 - 만든 사진을 올리고
-- 남이 좋아요를 누른다.
--
-- 두 테이블인 이유
-- 글(brags)과 좋아요(brag_likes)를 나눈다. 좋아요 수를 brags에 컬럼으로 두면
-- "내가 이 글에 좋아요를 눌렀는가"를 답할 수 없고, 중복 방지도 못 건다.
--
-- 레시피 추천 수와의 연결
-- 자랑 글의 좋아요는 그 글이 고른 레시피의 추천(recipe_likes)에도 반영한다. 다만
-- **사람당 레시피당 1회**다. 같은 레시피로 쓴 자랑 글이 여럿이고 한 사람이 전부
-- 좋아요를 눌러도 레시피 추천은 하나만 오른다. 유저 등록 레시피의 공개 기준이
-- 추천 3회인데(recommendation_agent.USER_RECIPE_MIN_LIKES), 그 기준이 한 사람에게
-- 휘둘리면 안 되기 때문이다. 이 규칙은 recipe_likes의 UNIQUE 제약이 강제한다.
--
-- 사용법: 008 다음에 적용한다.

BEGIN;

CREATE TABLE IF NOT EXISTS brags (
    id SERIAL PRIMARY KEY,
    -- 계정을 지우면 그 사람의 글도 함께 지운다. "요청하면 지웁니다"를 지키려면
    -- 남겨둘 수 없다(scripts/delete_account.py와 같은 방침).
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    -- 어떤 레시피로 만들었는지. 레시피가 지워지면 글도 함께 지운다 - 무엇을 만든
    -- 자랑인지 알 수 없는 글만 남기느니 없는 편이 낫다.
    recipe_id INTEGER NOT NULL REFERENCES recipes (id) ON DELETE CASCADE,
    -- Supabase Storage에 올린 사진의 공개 주소. 사진 없이 글만 올릴 수도 있다.
    image_url TEXT,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 피드는 최신순으로만 읽는다.
CREATE INDEX IF NOT EXISTS idx_brags_created_at ON brags (created_at DESC);
-- "이 레시피로 만든 자랑 글"을 레시피 상세에서 보여줄 때 쓴다.
CREATE INDEX IF NOT EXISTS idx_brags_recipe ON brags (recipe_id);

CREATE TABLE IF NOT EXISTS brag_likes (
    id SERIAL PRIMARY KEY,
    brag_id INTEGER NOT NULL REFERENCES brags (id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    -- 한 사람이 같은 글에 두 번 누를 수 없다. 화면에서도 막지만, 경합으로 두 번
    -- 들어오는 경우는 DB만 막을 수 있다(auth의 username UNIQUE와 같은 이유).
    UNIQUE (brag_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_brag_likes_brag ON brag_likes (brag_id);

-- recipe_likes에도 같은 제약이 필요하다. 지금까지는 화면이 한 번만 누르게 해서
-- 문제가 없었지만, 자랑 글 좋아요가 두 번째 경로로 생기면서 같은 사람이 같은
-- 레시피에 두 줄을 남길 수 있게 됐다. "사람당 레시피당 1회"를 DB가 강제한다.
--
-- 기존 중복이 있으면 UNIQUE를 못 건다. 먼저 지우고 건다(가장 오래된 것만 남긴다).
DELETE FROM recipe_likes a
      USING recipe_likes b
      WHERE a.id > b.id
        AND a.recipe_id = b.recipe_id
        AND a.user_id = b.user_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_recipe_likes_user_recipe
    ON recipe_likes (recipe_id, user_id);

COMMIT;
