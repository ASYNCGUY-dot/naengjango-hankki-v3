"""
간단한 토큰 기반 인가 (#인가공백 보완, 2026-07-19).

지금까지는 로그인이 user_id 하나만 돌려주고 이후 요청은 그 user_id를 그대로 믿었다 -
URL의 user_id만 바꾸면 남의 프로필/냉장고/후기를 읽고 쓸 수 있는 구멍이었다.

방식은 의도적으로 단순하게 유지한다(만료/갱신/리프레시 없음 - 이 규모에서는 과함):
- 로그인/회원가입 성공 시 secrets.token_urlsafe(32)로 토큰을 만들어 돌려주고,
  DB(auth_tokens)에는 sha256 해시만 저장한다 - DB가 유출돼도 토큰 원문은 알 수 없다.
- 이후 요청은 "Authorization: Bearer <토큰>" 헤더로 본인을 증명한다.
  get_current_user_id 의존성이 해시를 조회해 user_id로 바꿔주고, 각 엔드포인트는
  require_self()로 "토큰 주인 = 요청 대상 user_id"를 확인한다(불일치면 403).
- 로그아웃하면 해당 토큰 행을 지워서 즉시 무효화한다.
- 만료가 없는 대신 로그인할 때마다 새 토큰이 늘어나므로, 발급 시 같은 유저의
  오래된 토큰(가장 최근 5개 제외)을 정리한다.
"""

import hashlib
import secrets
import sqlite3
from datetime import datetime

from fastapi import Depends, Header, HTTPException

from api.deps import get_db

MAX_TOKENS_PER_USER = 5


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(cur, user_id: int) -> str:
    """새 토큰을 발급하고 해시를 저장한다. 원문 토큰은 이 반환값으로 딱 한 번만 노출된다."""
    token = secrets.token_urlsafe(32)
    cur.execute(
        "INSERT INTO auth_tokens (token_hash, user_id, created_at) VALUES (?, ?, ?)",
        (_hash_token(token), user_id, datetime.now().isoformat()),
    )
    # 만료 개념이 없으므로 로그인 반복 시 토큰이 무한히 쌓인다 - 최근 것만 남기고 정리.
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


def get_current_user_id(
    authorization: str | None = Header(default=None),
    cur: sqlite3.Cursor = Depends(get_db),
) -> int:
    """Authorization 헤더의 토큰을 검증해 user_id로 바꿔준다. FastAPI의 요청 단위
    의존성 캐시 덕분에 엔드포인트 본문과 같은 DB 커서를 공유한다(커넥션 이중 대여 없음)."""
    token = _extract_bearer(authorization)
    cur.execute("SELECT user_id FROM auth_tokens WHERE token_hash = ?", (_hash_token(token),))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다. 다시 로그인해주세요.")
    return row[0]


def require_self(claimed_user_id: int, current_user_id: int):
    """요청이 다루는 user_id가 토큰 주인 본인인지 확인한다."""
    if claimed_user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 계정의 데이터에만 접근할 수 있습니다.")
