"""
V1의 profile_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
validate_profile/update_user_profile은 수정하지 않고 그대로 가져다 쓴다.

V3 Phase 1(2026-08-12)에서 POST ""(인증 없이 users 행을 새로 만들던 엔드포인트)를
없앴다. 프로필은 이제 가입으로 이미 만들어진 계정에 PUT으로 붙인다 - 이유는
migration/005_users_username_required.sql에 정리했다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import profile_agent, recommendation_agent

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileRequest(BaseModel):
    gender: str
    age_group: str
    allergy: str
    health_goal: str
    purpose: str
    cooking_level: str
    supplements: str
    household_size: int
    novelty_pref: str
    cooking_tools: str
    medical_conditions: str = ""


class ProfileGetResponse(BaseModel):
    has_profile: bool
    gender: str | None = None
    age_group: str | None = None
    allergy: str | None = None
    health_goal: str | None = None
    purpose: str | None = None
    cooking_level: str | None = None
    supplements: str | None = None
    household_size: int | None = None
    novelty_pref: str | None = None
    cooking_tools: str | None = None
    medical_conditions: str | None = None


@router.get("/{user_id}", response_model=ProfileGetResponse)
def get_profile(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    profile = recommendation_agent.get_user_profile(cur, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    return ProfileGetResponse(
        # 온보딩을 마쳤는지의 판단 기준을 gender에서 health_goal로 옮겼다(2026-08-13).
        # 성별·연령대가 가입 단계로 올라가면서 gender는 가입 직후부터 채워져 있어,
        # 그걸로 판단하면 온보딩을 안 한 사람도 "마쳤다"가 된다.
        # health_goal은 온보딩에서만 채워지는 필수 항목이라 지금은 이쪽이 맞다.
        has_profile=profile["health_goal"] is not None,
        **{k: v for k, v in profile.items() if k != "id"},
    )


@router.put("/{user_id}")
def update_profile(
    user_id: int,
    body: ProfileRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    profile = body.model_dump()
    missing = profile_agent.validate_profile(profile)
    if missing:
        raise HTTPException(status_code=422, detail=f"필수 항목 누락: {missing}")
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    profile_agent.update_user_profile(cur, user_id, profile)
    return {"user_id": user_id, "updated": True}
