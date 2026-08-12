-- V3 Phase 1 (2026-08-12): auth_tokens에 만료 개념을 도입한다.
--
-- V2에는 만료가 없어서 한 번 발급된 토큰이 영구히 유효했다. 로그아웃하지 않은 기기의
-- 토큰도 계속 살아 있었고, 토큰이 유출되면 되돌릴 방법이 로그아웃뿐이었다.
-- api/auth_token.py가 expires_at을 읽고 쓰므로 배포 전에 이 파일을 먼저 적용해야 한다.
--
-- 사용법: 003_add_indexes.sql과 같다. POSTGRES_URL이 가리키는 Supabase Postgres에
-- psql이나 Supabase SQL editor로 직접 적용한다. 재실행해도 안전하게 IF NOT EXISTS를 쓴다.
--
-- 주의: 기존 토큰을 전부 지운다. 지금 로그인돼 있는 세션은 재로그인이 필요하다.
-- (2026-08-12 기준 17개, 전부 개발자 검증용 계정 것이다.) expires_at이 없는 토큰은
-- 코드가 "만료 판단 불가 = 만료됨"으로 처리하므로 어차피 통과하지 못한다. 남겨두면
-- 조회 대상으로만 남으므로 여기서 정리한다.
--
-- created_at 형식도 이 시점에 바뀐다. V2는 naive datetime.now()였고 V3는 UTC ISO
-- (오프셋 포함)다. 형식이 섞이면 ORDER BY created_at 문자열 정렬이 어긋나므로, 기존
-- 행을 지우는 것이 형식 통일을 겸한다.

ALTER TABLE auth_tokens ADD COLUMN IF NOT EXISTS expires_at TEXT;

DELETE FROM auth_tokens;

-- 만료가 생기면서 expires_at은 모든 행에 반드시 있어야 한다 - 없으면 만료 판단이 안 된다.
ALTER TABLE auth_tokens ALTER COLUMN expires_at SET NOT NULL;
ALTER TABLE auth_tokens ALTER COLUMN user_id SET NOT NULL;

-- 계정을 지우면 그 계정의 토큰도 함께 사라져야 한다. V2에는 이 외래키가 없어서
-- 계정을 지워도 토큰 행이 남는 구조였다.
ALTER TABLE auth_tokens DROP CONSTRAINT IF EXISTS auth_tokens_user_id_fkey;
ALTER TABLE auth_tokens
    ADD CONSTRAINT auth_tokens_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE;

-- issue_token()의 오래된 토큰 정리와 계정별 토큰 조회가 user_id로 필터링한다.
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id ON auth_tokens (user_id);
