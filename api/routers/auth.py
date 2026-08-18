"""
V1의 auth_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.

로그인 무차별 대입 방지: 이 라우터 계층에서만 아이디별 실패 횟수를 인메모리로 세서
잠깐 잠근다. HTTP 계층의 관심사라 auth_agent.py는 건드리지 않는다. Render 단일
인스턴스 기준 - 재시작/재배포되면 카운터가 초기화되지만 이 규모에서는 감내할 만하다.

비밀번호 최소 길이(MIN_PASSWORD_LENGTH): auth_agent.signup()은 비밀번호 형식을 전혀
검증하지 않아서(1글자도 통과) 이 라우터 계층에서 최소 길이만 확인한다 - 마찬가지로
HTTP 계층의 관심사라 auth_agent.py는 건드리지 않는다.

비밀번호 초기화(2026-08-13): "찾기"는 없다. 비밀번호는 단방향 해시로 저장돼 서버도
알 수 없으므로 알려줄 방법이 자체가 없다. 메일로 보낸 일회용 링크로 새 비밀번호를
설정하는 것만 가능하다.
"""

import os
import re
import sqlite3
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException

from pydantic import BaseModel, Field

from api import auth_token, usage_log
from api.deps import INTEGRITY_ERRORS, get_db
from src.agents import auth_agent, mail_agent

router = APIRouter(prefix="/auth", tags=["auth"])

MIN_PASSWORD_LENGTH = 8

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_WINDOW_SECONDS = 15 * 60

# 초기화 요청은 메일을 보내므로, 남이 같은 주소로 반복 요청해 메일함을 채우는 것을 막는다.
MAX_RESET_REQUESTS = 3
RESET_WINDOW_SECONDS = 60 * 60

# 메일에 담을 링크의 앞부분. 배포 시 정적 사이트 주소로 바꾼다.
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://localhost:5173")

_failed_login_attempts: dict[str, list[float]] = defaultdict(list)
_reset_requests: dict[str, list[float]] = defaultdict(list)

# 형식만 최소로 본다. 실제로 받는 주소인지는 메일이 도착하는지로만 확인된다.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _prune(bucket: dict[str, list[float]], key: str, window: int) -> list[float]:
    cutoff = time.time() - window
    kept = [t for t in bucket.get(key, []) if t > cutoff]
    bucket[key] = kept
    return kept


def _prune_old_attempts(username: str) -> list[float]:
    return _prune(_failed_login_attempts, username, LOGIN_LOCKOUT_WINDOW_SECONDS)


def _is_locked_out(username: str) -> bool:
    return len(_prune_old_attempts(username)) >= MAX_LOGIN_ATTEMPTS


def _record_failed_login(username: str):
    _prune_old_attempts(username)
    _failed_login_attempts[username].append(time.time())


def _clear_failed_logins(username: str):
    _failed_login_attempts.pop(username, None)


class Consents(BaseModel):
    """개인정보 수집 동의. 필수 둘은 True여야 가입이 된다."""

    terms_of_service: bool = False
    privacy: bool = False
    marketing: bool = False


class SignupRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    email: str = Field(min_length=1)
    gender: str = Field(min_length=1)
    age_group: str = Field(min_length=1)
    consents: Consents


class SignupResponse(BaseModel):
    user_id: int
    token: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user_id: int
    token: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetRequestResponse(BaseModel):
    """계정이 있든 없든 같은 응답을 준다 - 어떤 이메일이 가입돼 있는지 알아내는
    통로가 되면 안 되기 때문이다."""

    requested: bool


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


@router.post("/signup", response_model=SignupResponse)
def signup(body: SignupRequest, cur: sqlite3.Cursor = Depends(get_db)):
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"비밀번호는 최소 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.",
        )
    if not _EMAIL_RE.match(body.email.strip()):
        raise HTTPException(status_code=422, detail="이메일 형식이 올바르지 않습니다.")

    consents = body.consents.model_dump()
    if auth_agent.missing_required_consents(consents):
        raise HTTPException(
            status_code=422, detail="이용약관과 개인정보 수집·이용에 동의해야 가입할 수 있습니다."
        )

    # auth_agent.signup()은 SELECT로 중복을 확인한 뒤 INSERT한다. 그 사이에 같은
    # 아이디로 다른 요청이 끼어들면 확인은 통과하고 INSERT에서 UNIQUE 제약에 걸린다
    # (V3에서 users.username에 UNIQUE를 걸었다 - migration/005). 경합으로 진 쪽도
    # 결과는 "이미 존재하는 아이디"이므로 같은 409로 답한다.
    try:
        user_id = auth_agent.signup(
            cur,
            body.username,
            body.password,
            name=body.name,
            phone=body.phone,
            email=body.email,
            gender=body.gender,
            age_group=body.age_group,
        )
    except INTEGRITY_ERRORS:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디 또는 이메일입니다.")
    if user_id is None:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디 또는 이메일입니다.")

    auth_agent.record_consents(cur, user_id, consents)
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
    # Phase 4에서 "며칠째까지 돌아왔나"를 보려면 재방문 시점이 남아야 한다.
    usage_log.record(cur, usage_log.LOGIN, user_id=user_id)
    return LoginResponse(user_id=user_id, token=auth_token.issue_token(cur, user_id))


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), cur: sqlite3.Cursor = Depends(get_db)):
    """현재 토큰을 즉시 무효화한다. 헤더가 없거나 이미 무효한 토큰이어도 조용히 성공으로
    처리한다 - 로그아웃은 어차피 '로그인 안 된 상태로 만들기'가 목적이기 때문이다."""
    if authorization and authorization.startswith("Bearer "):
        auth_token.revoke_token(cur, authorization[len("Bearer "):].strip())
    return {"logged_out": True}


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
def request_password_reset(
    body: PasswordResetRequest, cur: sqlite3.Cursor = Depends(get_db)
):
    """초기화 링크를 메일로 보낸다.

    가입된 이메일이든 아니든 항상 같은 응답을 준다. 여기서 404를 주면 "이 주소는
    가입돼 있다/없다"를 확인하는 도구가 된다. 메일 발송이 실패해도 마찬가지다.
    """
    email = body.email.strip().lower()

    # 같은 주소로 반복 요청해 남의 메일함을 채우는 것을 막는다. 이 경우에도 응답은 같다.
    if len(_prune(_reset_requests, email, RESET_WINDOW_SECONDS)) >= MAX_RESET_REQUESTS:
        return PasswordResetRequestResponse(requested=True)
    _reset_requests[email].append(time.time())

    token = auth_agent.create_password_reset_token(cur, email)
    if token is not None:
        valid_minutes = int(auth_agent.RESET_TOKEN_TTL.total_seconds() // 60)
        subject, mail_body = mail_agent.build_password_reset_mail(
            f"{WEB_BASE_URL}/reset-password?token={token}", valid_minutes
        )
        # 발송 실패는 응답을 바꾸지 않는다. 실패를 드러내면 계정 존재 여부가 새어나간다.
        mail_agent.send_mail(email, subject, mail_body)

    return PasswordResetRequestResponse(requested=True)


@router.post("/password-reset/confirm")
def confirm_password_reset(
    body: PasswordResetConfirmRequest, cur: sqlite3.Cursor = Depends(get_db)
):
    if len(body.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"비밀번호는 최소 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.",
        )

    ok, message = auth_agent.reset_password_with_token(cur, body.token, body.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"reset": True, "detail": message}
