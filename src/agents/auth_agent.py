"""
Auth Agent [선택] - 유저 인증 (회원가입/로그인)
- 비밀번호는 그대로 저장하지 않고, salt를 붙여 PBKDF2로 해시해서 저장한다 (표준 라이브러리만 사용, 추가 설치 불필요).
- 로그인한 사용자는 users 테이블의 기존 행(user_id)을 계속 재사용한다.
  (게스트/비로그인 사용자는 지금처럼 매번 새 행을 만드는 기존 동작을 그대로 유지 - 하위 호환)
- 참고: 이건 학습용 MVP 수준의 인증이다. 실서비스로 확장한다면 더 강한 해시 파라미터,
  로그인 시도 제한, HTTPS 등 별도 보안 조치가 필요하다 (지침 8번 원칙과 동일).
"""

import os
import hashlib
import secrets
import sqlite3
from dotenv import load_dotenv

load_dotenv()
DB_PATH = "data/app.db"
ADMIN_SECRET = os.getenv("ADMIN_SECRET")


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


def signup(cur, username: str, password: str) -> int | None:
    """
    새 계정을 만든다. 프로필 항목(gender 등)은 일단 비워두고, 로그인 후
    추천을 받을 때 프로필 폼 제출 내용으로 채워 넣는다.
    이미 있는 아이디면 None을 반환한다.
    """
    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cur.fetchone() is not None:
        return None

    password_hash = hash_password(password)
    cur.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )
    return cur.lastrowid


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
    test_password = "pw1234"

    # 반복 실행해도 항상 같은 결과가 나오도록, 테스트 계정이 있으면 지우고 새로 만든다.
    cur.execute("DELETE FROM users WHERE username = ?", (test_username,))
    conn.commit()

    user_id = signup(cur, test_username, test_password)
    conn.commit()
    print(f"[회원가입] username={test_username} -> user_id={user_id}")

    dup = signup(cur, test_username, "다른비번")
    print(f"[중복 가입 시도] {dup} (None이어야 정상)")

    ok = login(cur, test_username, test_password)
    print(f"[정상 로그인] user_id={ok}")

    wrong = login(cur, test_username, "틀린비번")
    print(f"[틀린 비밀번호 로그인 시도] {wrong} (None이어야 정상)")

    not_exist = login(cur, "없는아이디", test_password)
    print(f"[존재하지 않는 아이디] {not_exist} (None이어야 정상)")

    conn.close()
