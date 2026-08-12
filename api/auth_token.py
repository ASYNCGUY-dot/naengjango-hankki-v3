"""
토큰 기반 인가 (#인가공백 보완, 2026-07-19 / 만료·갱신 도입 2026-08-12).

지금까지는 로그인이 user_id 하나만 돌려주고 이후 요청은 그 user_id를 그대로 믿었다 -
URL의 user_id만 바꾸면 남의 프로필/냉장고/후기를 읽고 쓸 수 있는 구멍이었다.

방식:
- 로그인/회원가입 성공 시 secrets.token_urlsafe(32)로 토큰을 만들어 돌려주고,
  DB(auth_tokens)에는 sha256 해시만 저장한다 - DB가 유출돼도 토큰 원문은 알 수 없다.
- 이후 요청은 "Authorization: Bearer <토큰>" 헤더로 본인을 증명한다.
  get_current_user_id 의존성이 해시를 조회해 user_id로 바꿔주고, 각 엔드포인트는
  require_self()로 "토큰 주인 = 요청 대상 user_id"를 확인한다(불일치면 403).
- 로그아웃하면 해당 토큰 행을 지워서 즉시 무효화한다.
- 발급 시 같은 유저의 오래된 토큰(가장 최근 MAX_TOKENS_PER_USER개 제외)을 정리한다.

만료·갱신 (2026-08-12, V3 Phase 1):
V2에는 만료가 아예 없어서, 토큰이 한 번 새면 영구히 유효했다. 로그아웃하지 않은
기기의 토큰도 계속 살아 있었다. 이제 발급 시점에 expires_at을 박고 매 요청마다
확인한다.

"쓰고 있으면 계속 유지되고, 안 쓰면 만료된다"가 목표라 절대 만료가 아니라 슬라이딩
방식이다. 다만 요청마다 UPDATE를 쓰면 무료 티어(0.1 CPU)에서 낭비가 크므로, 남은
수명이 절반 밑으로 떨어졌을 때만 연장한다 - 정상 사용 중이면 30일마다 한 번꼴로만
쓰기가 발생한다.

시각은 UTC ISO 문자열로 저장한다. 문자열 비교만으로 정렬·만료 판단이 되도록 형식을
한 가지로 통일한 것이다. V2가 쓰던 naive datetime.now() 값과는 형식이 다르므로,
마이그레이션(004)에서 기존 토큰을 전부 지워 재로그인을 강제한다.
"""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException

from api.deps import get_db

MAX_TOKENS_PER_USER = 5

TOKEN_TTL = timedelta(days=30)
# 남은 수명이 이 값 밑으로 떨어지면 연장한다(요청마다 쓰지 않기 위한 문턱).
TOKEN_SLIDE_THRESHOLD = TOKEN_TTL / 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(cur, user_id: int) -> str:
    """새 토큰을 발급하고 해시를 저장한다. 원문 토큰은 이 반환값으로 딱 한 번만 노출된다."""
    token = secrets.token_urlsafe(32)
    now = _now()
    cur.execute(
        "INSERT INTO auth_tokens (token_hash, user_id, created_at, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (_hash_token(token), user_id, now.isoformat(), (now + TOKEN_TTL).isoformat()),
    )
    # 로그인 반복 시 토큰이 쌓이는 것을 막는다 - 최근 것만 남기고 정리.
    cur.execute(
        "DELETE FROM auth_tokens WHERE user_id = ? AND token_hash NOT IN ("
        "SELECT token_hash FROM auth_tokens WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT ?)",
        (user_id, user_id, MAX_TOKENS_PER_USER),
    )
    return token


def revoke_token(cur, token: str):
    cur.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (_hash_token(token),))


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return authorization[len("Bearer "):].strip()


def _parse_expires_at(value) -> datetime | None:
    """저장된 expires_at을 datetime으로 바꾼다. 값이 없거나 형식이 깨졌으면 None -
    호출부에서 "만료된 것으로 취급"한다. 만료 판단을 못 하는 토큰을 통과시키면
    만료를 도입한 의미가 없기 때문이다."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def get_current_user_id(
    authorization: str | None = Header(default=None),
    cur: sqlite3.Cursor = Depends(get_db),
) -> int:
    """Authorization 헤더의 토큰을 검증해 user_id로 바꿔준다. FastAPI의 요청 단위
    의존성 캐시 덕분에 엔드포인트 본문과 같은 DB 커서를 공유한다(커넥션 이중 대여 없음)."""
    token = _extract_bearer(authorization)
    token_hash = _hash_token(token)
    cur.execute(
        "SELECT user_id, expires_at FROM auth_tokens WHERE token_hash = ?", (token_hash,)
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다. 다시 로그인해주세요.")

    user_id, expires_at_raw = row
    expires_at = _parse_expires_at(expires_at_raw)
    now = _now()
    if expires_at is None or expires_at <= now:
        # 만료된 행을 그대로 두면 계속 조회 대상으로 남으므로 여기서 치운다.
        cur.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (token_hash,))
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다. 다시 로그인해주세요.")

    # 슬라이딩 연장: 남은 수명이 문턱 밑일 때만 쓴다(요청마다 UPDATE하지 않기 위함).
    if expires_at - now < TOKEN_SLIDE_THRESHOLD:
        cur.execute(
            "UPDATE auth_tokens SET expires_at = ? WHERE token_hash = ?",
            ((now + TOKEN_TTL).isoformat(), token_hash),
        )
    return user_id


def require_self(claimed_user_id: int, current_user_id: int):
    """요청이 다루는 user_id가 토큰 주인 본인인지 확인한다."""
    if claimed_user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 계정의 데이터에만 접근할 수 있습니다.")
