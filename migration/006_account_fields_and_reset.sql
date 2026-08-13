-- V3 (2026-08-13): 회원가입 정보 확장 + 동의 기록 + 비밀번호 초기화
--
-- 배경
-- V2의 계정은 아이디와 비밀번호뿐이었다. 그래서 두 가지가 불가능했다.
--   1) 비밀번호를 잊으면 복구할 방법이 없다(연락 수단이 없음)
--   2) 가입 시점을 모른다 - users에만 created_at이 없어서, Phase 4에서 "가입하고 얼마 만에
--      재료를 넣었나 / 가입만 하고 안 돌아온 사람이 누구인가"를 볼 수 없다
--
-- 사용법: 004, 005와 같다. 005 다음에 적용한다.
--
-- 적용 순서 주의: 005가 계정을 정리해 최지수 한 행만 남긴다. 그 행에는 이메일이 없으므로
-- 아래 email 컬럼은 NOT NULL로 걸지 않는다. 대신 UNIQUE 인덱스를 걸고, 신규 가입에서는
-- API가 필수로 받는다(api/routers/auth.py). 남은 계정에 이메일을 채운 뒤에는
-- ALTER TABLE users ALTER COLUMN email SET NOT NULL을 따로 걸면 된다.

BEGIN;

-- ---------- 1. 계정 정보 확장 ----------
ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TEXT;

-- 이메일은 비밀번호 초기화의 대상을 특정하는 값이라 중복되면 안 된다.
-- 대소문자를 구분하지 않는다("A@x.com"과 "a@x.com"은 같은 주소다).
-- Postgres는 UNIQUE 인덱스에서 NULL을 서로 다른 값으로 보므로, 이메일이 없는 기존 행은
-- 이 제약에 걸리지 않는다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));

-- 가입 시점을 모르는 기존 행은 소급할 수 없다. 비워둔 채로 두고, 앞으로 만들어지는
-- 계정만 값을 갖는다. 분석할 때 NULL은 "V3 이전 계정"으로 읽으면 된다.

-- ---------- 2. 동의 기록 ----------
-- 개인정보를 수집하므로 동의를 받고 그 사실을 남긴다. 증빙이 목적이라 덮어쓰지 않고
-- 이력으로 쌓는다 - "언제 어떤 버전에 동의했는가"가 나중에 필요한 정보이고, 철회하면
-- agreed=false인 행이 하나 더 쌓이는 방식이라야 이력이 보존된다.
CREATE TABLE IF NOT EXISTS user_consents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    -- 'terms_of_service' | 'privacy' | 'marketing'
    consent_key TEXT NOT NULL,
    -- 약관 문서의 버전. 문서를 고치면 새 버전으로 다시 받아야 한다.
    version TEXT NOT NULL,
    agreed BOOLEAN NOT NULL,
    agreed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_consents_user_id ON user_consents (user_id);

-- ---------- 3. 비밀번호 초기화 토큰 ----------
-- "찾기"가 아니라 "초기화"다. 기존 비밀번호를 알려주는 방법은 없다(단방향 해시라
-- 서버도 모른다). 메일로 보낸 일회용 토큰으로 새 비밀번호를 설정한다.
--
-- auth_tokens와 같은 원칙으로 원문이 아니라 sha256 해시만 저장한다 - DB가 유출돼도
-- 그 토큰으로 남의 비밀번호를 바꿀 수 없어야 한다.
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    -- 한 번 쓴 토큰은 다시 못 쓴다. 지우지 않고 표시만 하는 이유는, 이미 쓴 링크를 다시
    -- 눌렀을 때 "만료됨"이 아니라 "이미 사용됨"으로 구분해 안내할 수 있어서다.
    used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id
    ON password_reset_tokens (user_id);

COMMIT;

-- 적용 후 확인용:
--   SELECT column_name FROM information_schema.columns
--    WHERE table_schema='public' AND table_name='users'
--      AND column_name IN ('name','phone','email','created_at');
--   -- 네 개가 모두 나와야 한다.
