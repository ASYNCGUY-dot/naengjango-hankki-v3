-- V3 Phase 1 (2026-08-12): 계정 데이터를 정리하고 username에 제약을 건다.
--
-- 배경
-- V2의 users 테이블은 username과 password_hash가 둘 다 nullable이었고 UNIQUE 제약도
-- 없었다. 문제가 셋이다.
--   1) POST /profile이 인증 없이 username/password 없는 행을 새로 만들었다. 2026-08-12
--      기준 43개 계정 중 34개가 이 경로로 생긴 빈 행이다(참조 테이블 9곳 전부 확인,
--      참조 0개). V3에서 이 엔드포인트를 없앴다 - 프로필은 가입으로 만들어진 계정에
--      PUT으로 붙인다.
--   2) UNIQUE가 없어서 auth_agent.signup()의 "SELECT로 중복 확인 후 INSERT"가 경합에
--      취약했다. 동시 요청 둘이 같은 아이디로 모두 통과할 수 있었다. DB 제약으로 막는다.
--   3) 남은 계정 대부분이 검증용이라 실사용 데이터와 섞여 있었다.
--
-- 지금이 유일한 적기다. 실사용자가 한 명이라도 생기면 이 정리는 마이그레이션 부담이 된다.
--
-- 사용법: 004와 같다. POSTGRES_URL이 가리키는 Supabase Postgres에 psql이나 Supabase
-- SQL editor로 적용한다. 004를 먼저 적용해야 한다(auth_tokens 외래키가 CASCADE로
-- 바뀌어 있어야 계정 삭제 시 토큰이 함께 정리된다).
--
-- 주의: 되돌릴 수 없다. 계정 42개와 그에 딸린 데이터를 지운다. 적용 전에 Supabase
-- 대시보드에서 백업을 한 번 받아두는 편이 안전하다.

BEGIN;

-- 지울 대상: username이 없는 행 전부 + 이름이 확인된 검증 계정.
-- 최지수(유일한 관리자, 재료 11개·후기 1개 보유)만 남긴다.
CREATE TEMP TABLE doomed_users ON COMMIT DROP AS
SELECT id FROM users
WHERE username IS NULL
   OR username = ''
   OR username IN (
        'testuser01', 'test', 'gaptest0718', 'design_verify_20260726',
        'verify_ui_v2_20260721', 'prod_verify_20260721', 'design2_verify_local',
        '최지목'
      );

-- 안전장치: 관리자 계정이 삭제 대상에 들어갔거나 남는 계정이 없으면 즉시 중단한다.
-- 조건식을 잘못 써서 전부 지우는 사고를 막기 위한 것이다.
DO $$
DECLARE
    total INT;
    survivors INT;
    admins_left INT;
BEGIN
    SELECT COUNT(*) INTO total FROM users;
    -- 빈 DB(CI가 001부터 순서대로 재생하는 경우)에는 지울 것도 지킬 것도 없다.
    -- 이 경우까지 예외로 막으면 마이그레이션 체인 자체가 재생되지 않는다.
    IF total = 0 THEN
        RETURN;
    END IF;

    SELECT COUNT(*) INTO survivors
    FROM users WHERE id NOT IN (SELECT id FROM doomed_users);

    SELECT COUNT(*) INTO admins_left
    FROM users WHERE is_admin = 1 AND id NOT IN (SELECT id FROM doomed_users);

    IF survivors = 0 THEN
        RAISE EXCEPTION '남는 계정이 없다. 삭제 조건을 확인할 것.';
    END IF;
    IF admins_left = 0 THEN
        RAISE EXCEPTION '관리자 계정이 남지 않는다. 삭제 조건을 확인할 것.';
    END IF;
END $$;

-- 외래키가 걸린 자식 행을 먼저 지운다. 001_schema.sql의 참조에는 ON DELETE 규칙이
-- 없어서, 이 순서를 지키지 않으면 users 삭제가 외래키 위반으로 실패한다.
DELETE FROM ingredients            WHERE user_id      IN (SELECT id FROM doomed_users);
DELETE FROM reviews                WHERE user_id      IN (SELECT id FROM doomed_users);
DELETE FROM favorites              WHERE user_id      IN (SELECT id FROM doomed_users);
DELETE FROM ingredient_favorites   WHERE user_id      IN (SELECT id FROM doomed_users);
DELETE FROM recipe_likes           WHERE user_id      IN (SELECT id FROM doomed_users);
DELETE FROM user_partner_keys      WHERE user_id      IN (SELECT id FROM doomed_users);
DELETE FROM auth_tokens            WHERE user_id      IN (SELECT id FROM doomed_users);
DELETE FROM ingredient_submissions WHERE submitted_by IN (SELECT id FROM doomed_users);

-- 남은 제출 건의 심사자만 지워지는 경우는 제출 자체를 없앨 이유가 없다. 심사 이력만 비운다.
UPDATE ingredient_submissions SET reviewed_by = NULL
WHERE reviewed_by IN (SELECT id FROM doomed_users);

DELETE FROM users WHERE id IN (SELECT id FROM doomed_users);

-- 이제 남은 행은 전부 username과 password_hash를 갖고 있다.
ALTER TABLE users ALTER COLUMN username SET NOT NULL;
ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;

-- signup()의 중복 확인이 경합에 지지 않도록 DB에서 막는다.
-- 라우터는 이 제약 위반을 409로 바꿔 응답한다(api/routers/auth.py).
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;
ALTER TABLE users ADD CONSTRAINT users_username_key UNIQUE (username);

COMMIT;

-- 적용 후 확인용 (직접 실행해서 눈으로 볼 것):
--   SELECT id, username, is_admin FROM users ORDER BY id;
--   -- 최지수 한 행만 남아야 한다.
