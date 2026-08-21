-- V3 (2026-08-22): 피드백 - 지인 테스트에서 "불편했던 것"을 앱 안에서 받는다
--
-- 배경
-- Phase 4의 목표는 기능 확인이 아니라 "어디서 멈추는가"를 아는 것이다. 그런데
-- usage_events는 멈춘 자리만 알려주고 **왜** 멈췄는지는 말해주지 않는다. 그건
-- 사람이 적어줘야만 알 수 있다.
--
-- 카톡으로 받아도 되지만 두 가지가 아쉽다. 며칠 지나면 대화에 묻히고, 누가 어느
-- 시점에 무엇 때문에 막혔는지를 사용 기록과 맞춰 보기 어렵다. user_id를 달아두면
-- 그 사람의 usage_events와 나란히 놓고 읽을 수 있다.
--
-- 왜 후기(reviews)와 따로인가
-- 후기는 "이 레시피가 어땠나"이고 레시피에 붙는다. 피드백은 "이 앱이 어땠나"라
-- 붙을 레시피가 없다. 같은 테이블에 넣으면 recipe_id가 NULL인 행이 섞여서
-- 레시피 화면의 후기 목록을 매번 걸러내야 한다.
--
-- 누가 보는가
-- 쓴 사람은 자기 글만, 관리자는 전부 본다. 사용자 테스트에서 남의 의견이 보이면
-- 그쪽으로 끌려가서, 두 번째 사람부터는 자기 생각이 아니라 "나도 그랬어"를 쓴다.
--
-- 사용법: 009 다음에 적용한다.

BEGIN;

CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    -- 계정을 지우면 그 사람의 글도 함께 지운다("요청하면 지웁니다"를 지키려면
    -- 남겨둘 수 없다). 익명 제보는 받지 않는다 - 누가 어느 단계에서 막혔는지를
    -- 사용 기록과 맞춰 보는 것이 이 테이블의 존재 이유다.
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 관리자 화면은 최신순으로만 읽는다.
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at DESC);
-- 본인 글 조회.
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback (user_id);

COMMIT;
