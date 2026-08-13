"""
Auth Agent - 유저 인증 (회원가입/로그인/비밀번호 초기화)
- 비밀번호는 그대로 저장하지 않고, salt를 붙여 PBKDF2로 해시해서 저장한다 (표준 라이브러리만 사용).
- 참고: 이건 학습용 MVP 수준의 인증이다. 실서비스로 확장한다면 더 강한 해시 파라미터,
  로그인 시도 제한, HTTPS 등 별도 보안 조치가 필요하다.

2026-08-13 (V3): 가입 정보를 넓히고 비밀번호 초기화를 붙였다.
V2의 계정은 아이디와 비밀번호뿐이라 비밀번호를 잊으면 복구할 방법이 없었고, 가입 시점도
남지 않아 "가입하고 얼마 만에 썼나"를 볼 수 없었다.
"""

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()
DB_PATH = "data/app.db"
ADMIN_SECRET = os.getenv("ADMIN_SECRET")

# 개인정보 수집 동의를 받아야 하는 항목. 필수 둘은 없으면 가입이 성립하지 않고,
# 마케팅은 선택이라 거절해도 가입된다.
REQUIRED_CONSENTS = ("terms_of_service", "privacy")
OPTIONAL_CONSENTS = ("marketing",)
ALL_CONSENTS = REQUIRED_CONSENTS + OPTIONAL_CONSENTS

# 약관 문서를 고치면 이 값을 올린다. 그러면 "어느 버전에 동의했는가"가 기록으로 남는다.
CONSENT_VERSION = "2026-08-13"

# 초기화 링크의 유효시간. 길면 메일함이 털렸을 때 위험이 오래 남고, 너무 짧으면
# 메일 확인이 늦는 사람이 못 쓴다.
RESET_TOKEN_TTL = timedelta(minutes=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str, salt: str | None = None) -> str:
    """salt가 없으면 새로 만들고, "salt$해시" 형태의 문자열을 반환한다."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """저장된 해시에서 salt를 꺼내 같은 방식으로 다시 해시해보고 일치하는지 비교한다."""
    if not stored_hash or "$" not in stored_hash:
        return False
    salt, _ = stored_hash.split("$", 1)
    return hash_password(password, salt) == stored_hash


def signup(
    cur,
    username: str,
    password: str,
    *,
    name: str,
    phone: str,
    email: str,
    gender: str,
    age_group: str,
) -> int | None:
    """
    새 계정을 만든다. 이미 있는 아이디나 이메일이면 None을 반환한다.

    성별·연령대는 원래 온보딩에서 받던 프로필 항목인데, 같은 users 행에 들어가므로
    가입 시점에 받아도 컬럼은 그대로다. 나머지 프로필(알레르기·건강목표 등)은 여전히
    가입 후 온보딩에서 채운다.
    """
    email_normalized = email.strip().lower()

    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cur.fetchone() is not None:
        return None

    # 이메일이 초기화 대상을 특정하므로 중복을 허용하면 누구 계정을 초기화할지 정할 수 없다.
    cur.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email_normalized,))
    if cur.fetchone() is not None:
        return None

    cur.execute(
        "INSERT INTO users (username, password_hash, name, phone, email, gender, age_group, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            username,
            hash_password(password),
            name.strip(),
            phone.strip(),
            email_normalized,
            gender,
            age_group,
            _now().isoformat(),
        ),
    )
    return cur.lastrowid


def missing_required_consents(consents: dict[str, bool]) -> list[str]:
    """필수 동의 중 빠진 것을 돌려준다. 비어 있으면 통과."""
    return [key for key in REQUIRED_CONSENTS if not consents.get(key, False)]


def record_consents(cur, user_id: int, consents: dict[str, bool]) -> None:
    """동의 내역을 이력으로 남긴다.

    덮어쓰지 않고 계속 쌓는 이유는 증빙이 목적이기 때문이다. 나중에 철회하면 agreed=false인
    행이 하나 더 생기고, "언제 어떤 버전에 동의했다가 언제 철회했는가"가 그대로 남는다.
    거절도 기록한다 - 행이 없으면 "안 물어봤다"와 "거절했다"를 구분할 수 없다.
    """
    agreed_at = _now().isoformat()
    for key in ALL_CONSENTS:
        cur.execute(
            "INSERT INTO user_consents (user_id, consent_key, version, agreed, agreed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, key, CONSENT_VERSION, bool(consents.get(key, False)), agreed_at),
        )


def login(cur, username: str, password: str) -> int | None:
    """아이디/비밀번호가 맞으면 user_id, 아니면 None을 반환한다."""
    cur.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if row is None:
        return None
    user_id, stored_hash = row
    if verify_password(password, stored_hash):
        return user_id
    return None


def create_password_reset_token(cur, email: str) -> str | None:
    """이메일에 해당하는 계정이 있으면 일회용 토큰 원문을 만들어 돌려준다.

    "찾기"가 아니라 "초기화"다. 기존 비밀번호는 단방향 해시라 서버도 알 수 없으므로
    알려줄 방법이 없다. 새 비밀번호를 설정할 수 있는 링크를 보내는 것이 전부다.

    원문은 이 반환값으로 한 번만 나가고 DB에는 해시만 남는다(auth_tokens와 같은 원칙).
    계정이 없으면 None인데, 호출부는 이 차이를 응답에 드러내면 안 된다 - 어떤 이메일이
    가입돼 있는지 알아내는 통로가 되기 때문이다.
    """
    cur.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email.strip().lower(),))
    row = cur.fetchone()
    if row is None:
        return None
    user_id = row[0]

    # 새로 요청하면 이전 링크는 무효가 되는 게 자연스럽다. 여러 개가 동시에 살아 있으면
    # 오래된 메일의 링크로도 비밀번호가 바뀐다.
    cur.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
        (_now().isoformat(), user_id),
    )

    token = secrets.token_urlsafe(32)
    now = _now()
    cur.execute(
        "INSERT INTO password_reset_tokens (token_hash, user_id, created_at, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (_hash_token(token), user_id, now.isoformat(), (now + RESET_TOKEN_TTL).isoformat()),
    )
    return token


def reset_password_with_token(cur, token: str, new_password: str) -> tuple[bool, str]:
    """토큰을 확인하고 비밀번호를 바꾼다. (성공 여부, 사유)를 돌려준다."""
    token_hash = _hash_token(token)
    cur.execute(
        "SELECT user_id, expires_at, used_at FROM password_reset_tokens WHERE token_hash = ?",
        (token_hash,),
    )
    row = cur.fetchone()
    if row is None:
        return False, "유효하지 않은 링크입니다. 초기화를 다시 요청해주세요."

    user_id, expires_at_raw, used_at = row
    if used_at is not None:
        # 만료와 구분해서 안내한다. 이미 바꾼 사람이 옛 링크를 다시 누른 경우다.
        return False, "이미 사용된 링크입니다. 새 비밀번호로 로그인해주세요."

    try:
        expires_at = datetime.fromisoformat(str(expires_at_raw))
    except (TypeError, ValueError):
        return False, "유효하지 않은 링크입니다. 초기화를 다시 요청해주세요."
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now():
        return False, "만료된 링크입니다. 초기화를 다시 요청해주세요."

    cur.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    cur.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?",
        (_now().isoformat(), token_hash),
    )
    # 비밀번호를 바꿨으면 기존 로그인 세션도 끊는다. 누가 몰래 로그인해 있었다면
    # 비밀번호만 바꿔서는 쫓아낼 수 없다.
    cur.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
    return True, "비밀번호가 변경되었습니다."


def promote_to_admin(cur, user_id: int, code: str) -> bool:
    """
    .env의 ADMIN_SECRET과 일치하는 코드를 입력한 경우에만 이 계정을 관리자로 승격한다.
    관리자 지정 UI에서 "누가 첫 관리자가 되는가"라는 순환 문제를 피하기 위한 방식이다
    (코드를 아는 사람만 스스로를 관리자로 전환할 수 있음 - DB를 직접 건드릴 필요가 없다).
    """
    if not ADMIN_SECRET or not code or code != ADMIN_SECRET:
        return False
    cur.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
    return True


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    test_username = "testuser01"
    test_password = "pw12345678"
    test_account = {
        "name": "테스트",
        "phone": "010-0000-0000",
        "email": "testuser01@example.com",
        "gender": "여성",
        "age_group": "20대",
    }

    # 반복 실행해도 항상 같은 결과가 나오도록, 테스트 계정이 있으면 지우고 새로 만든다.
    cur.execute("DELETE FROM users WHERE username = ?", (test_username,))
    conn.commit()

    user_id = signup(cur, test_username, test_password, **test_account)
    conn.commit()
    print(f"[회원가입] username={test_username} -> user_id={user_id}")

    dup = signup(cur, test_username, "다른비번12345", **test_account)
    print(f"[중복 가입 시도] {dup} (None이어야 정상)")

    ok = login(cur, test_username, test_password)
    print(f"[정상 로그인] user_id={ok}")

    wrong = login(cur, test_username, "틀린비번12345")
    print(f"[틀린 비밀번호 로그인 시도] {wrong} (None이어야 정상)")

    not_exist = login(cur, "없는아이디", test_password)
    print(f"[존재하지 않는 아이디] {not_exist} (None이어야 정상)")

    conn.close()
