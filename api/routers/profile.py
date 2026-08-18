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

from api import usage_log
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
    # 마이 화면이 "누구로 로그인했는지"를 보여주는 데 쓴다(2026-08-13).
    username: str | None = None
    name: str | None = None
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


class AllergyOption(BaseModel):
    """화면에 보여줄 이름과, 서버에 저장할 값."""

    label: str
    value: str
    recipe_count: int


# "/allergy-options"는 "/{user_id}"보다 먼저 등록해야 한다 - 뒤에 두면 "allergy-options"가
# user_id 자리에 매칭되다 int 변환에 실패해 422가 난다(8.2 함정).
@router.get("/allergy-options", response_model=list[AllergyOption])
def list_allergy_options(cur: sqlite3.Cursor = Depends(get_db)):
    """온보딩에서 고를 알레르기 목록을 실제 태그에서 만든다.

    화면이 목록을 지어내면 안 된다. 태그에 없는 값을 고르게 하면 사용자는 골랐는데
    필터는 아무것도 안 거르고, 본인은 걸러졌다고 믿는다. 실제로 기존 데이터에
    "콩"(태그는 "대두"), "@$#$" 같은 자유 입력이 남아 있다.

    동의어는 하나로 묶어서 보여준다(달걀/계란처럼 원본 표기가 갈린 것들).
    """
    cur.execute(
        "SELECT tag_value, COUNT(DISTINCT recipe_id) FROM recipe_tags "
        "WHERE tag_type = 'allergy' GROUP BY tag_value"
    )
    counts = {row[0]: row[1] for row in cur.fetchall()}

    options: list[AllergyOption] = []
    covered: set[str] = set()
    for group in recommendation_agent.ALLERGY_SYNONYMS:
        present = [name for name in group if name in counts]
        if not present:
            continue
        # 가장 많이 쓰인 표기를 대표로 삼는다.
        label = max(present, key=lambda name: counts[name])
        options.append(
            AllergyOption(
                label=label, value=label, recipe_count=sum(counts[name] for name in present)
            )
        )
        covered |= set(group)

    for name, count in counts.items():
        if name in covered:
            continue
        options.append(AllergyOption(label=name, value=name, recipe_count=count))

    options.sort(key=lambda option: option.recipe_count, reverse=True)
    return options


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
    # health_goal을 함께 읽는다. 온보딩을 "처음" 마친 시점을 알려면 고치기 전 상태가
    # 필요한데, 존재 확인 쿼리가 이미 있으므로 왕복을 더 늘리지 않고 끼워 읽는다.
    cur.execute("SELECT id, health_goal FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    was_onboarded = bool(row[1])
    profile_agent.update_user_profile(cur, user_id, profile)
    # 수정할 때마다 남기면 "온보딩을 언제 마쳤나"가 마지막 수정 시각으로 흐려진다.
    if not was_onboarded:
        usage_log.record(cur, usage_log.ONBOARDING_DONE, user_id=user_id)
    return {"user_id": user_id, "updated": True}
