"""
V1의 auth_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
signup/login 함수 자체는 수정하지 않고 그대로 가져다 쓴다.

로그인 무차별 대입 방지: 이 라우터 계층에서만 아이디별 실패 횟수를 인메모리로 세서
잠깐 잠근다. HTTP 계층의 관심사라 auth_agent.py는 건드리지 않는다. Render 단일
인스턴스 기준 - 재시작/재배포되면 카운터가 초기화되지만 이 규모에서는 감내할 만하다.

비밀번호 최소 길이(MIN_PASSWORD_LENGTH): auth_agent.signup()은 비밀번호 형식을 전혀
검증하지 않아서(1글자도 통과) 이 라우터 계층에서 최소 길이만 확인한다 - 마찬가지로
HTTP 계층의 관심사라 auth_agent.py는 건드리지 않는다.
"""

import sqlite3
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException

from pydantic import BaseModel

from api import auth_token
from api.deps import get_db
from src.agents import auth_agent

router = APIRouter(prefix="/auth", tags=["auth"])

MIN_PASSWORD_LENGTH = 8

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_WINDOW_SECONDS = 15 * 60

_failed_login_attempts: dict[str, list[float]] = defaultdict(list)


def _prune_old_attempts(username: str) -> list[float]:
    cutoff = time.time() - LOGIN_LOCKOUT_WINDOW_SECONDS
    attempts = [t for t in _failed_login_attempts.get(username, []) if t > cutoff]
    _failed_login_attempts[username] = attempts
    return attempts


def _is_locked_out(username: str) -> bool:
    return len(_prune_old_attempts(username)) >= MAX_LOGIN_ATTEMPTS


def _record_failed_login(username: str):
    _prune_old_attempts(username)
    _failed_login_attempts[username].append(time.time())


def _clear_failed_logins(username: str):
    _failed_login_attempts.pop(username, None)


class SignupRequest(BaseModel):
    username: str
    password: str


class SignupResponse(BaseModel):
    user_id: int
    token: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user_id: int
    token: str


@router.post("/signup", response_model=SignupResponse)
def signup(body: SignupRequest, cur: sqlite3.Cursor = Depends(get_db)):
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"비밀번호는 최소 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.",
        )
    user_id = auth_agent.signup(cur, body.username, body.password)
    if user_id is None:
        raise HTTPException(status_code=409, detail="이미 존재하는 아이디입니다.")
    return SignupResponse(user_id=user_id, token=auth_token.issue_token(cur, user_id))


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, cur: sqlite3.Cursor = Depends(get_db)):
    if _is_locked_out(body.username):
        raise HTTPException(
            status_code=429,
            detail=f"로그인 시도가 너무 많습니다. {LOGIN_LOCKOUT_WINDOW_SECONDS // 60}분 후 다시 시도해주세요.",
        )
    user_id = auth_agent.login(cur, body.username, body.password)
    if user_id is None:
        _record_failed_login(body.username)
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    _clear_failed_logins(body.username)
    return LoginResponse(user_id=user_id, token=auth_token.issue_token(cur, user_id))


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), cur: sqlite3.Cursor = Depends(get_db)):
    """현재 토큰을 즉시 무효화한다. 헤더가 없거나 이미 무효한 토큰이어도 조용히 성공으로
    처리한다 - 로그아웃은 어차피 '로그인 안 된 상태로 만들기'가 목적이기 때문이다."""
    if authorization and authorization.startswith("Bearer "):
        auth_token.revoke_token(cur, authorization[len("Bearer "):].strip())
    return {"logged_out": True}
