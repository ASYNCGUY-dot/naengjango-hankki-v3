"""유저 본인의 쿠팡파트너스 키 등록·해제 (#95).

유저가 등록한 레시피의 추천이 기준치를 넘으면, 그 레시피의 재료 구매 링크가 작성자
본인의 제휴 키로 만들어져 수수료가 작성자에게 간다. 그러려면 작성자의 키를 받아 둬야
한다.

이 라우터가 지키는 규칙 셋:

1. **저장한 키는 절대 돌려주지 않는다.** 조회는 "등록했는지 여부"와 "언제 갱신했는지"만
   준다. 화면이 키를 다시 보여줄 이유가 없고, 한 번이라도 응답에 실으면 로그·캐시·
   브라우저 히스토리로 새어나갈 자리가 그만큼 늘어난다.
2. **본인 것만 만진다.** require_self로 막는다. 관리자도 예외가 아니다 - 남의 제휴
   수익 계정을 운영자가 바꿀 수 있어야 할 이유가 없다.
3. **평문으로 저장하지 않는다.** crypto_utils가 Fernet으로 암호화하고, 실제로 쓰는
   순간에만 메모리에서 푼다.

쿠팡 최종승인(누적 판매 15만원) 전에는 Deeplink API가 안 열려서 등록해도 변환이
실패한다. 그건 정상 상태이고, 그때는 아무 키도 안 붙은 일반 검색 링크가 된다
(shopping_agent.coupang_search_url 참고).
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import shopping_agent
from src.agents.recommendation_agent import USER_RECIPE_REVENUE_MIN_LIKES

router = APIRouter(prefix="/partner-keys", tags=["partner-keys"])


class PartnerKeyIn(BaseModel):
    # 쿠팡이 주는 키의 정확한 길이를 문서로 확인하지 못해 상한만 넉넉히 둔다. 빈 값과
    # 실수로 붙은 공백만 여기서 막고, 맞는 키인지는 실제 호출이 판정한다.
    access_key: str = Field(min_length=8, max_length=256)
    secret_key: str = Field(min_length=8, max_length=256)


class PartnerKeyStatus(BaseModel):
    registered: bool
    updated_at: str | None = None
    # 수익이 작성자에게 넘어가는 추천 수. 화면이 이 숫자를 따로 들고 있으면 기준이
    # 바뀔 때 조용히 어긋난다 - 이 프로젝트에서 가장 비싸게 배운 것이 그거다
    # (성별·연령대·병력 선택지, 냉장고 자동완성과 같은 원칙).
    revenue_min_likes: int = USER_RECIPE_REVENUE_MIN_LIKES


@router.get("/{user_id}", response_model=PartnerKeyStatus)
def get_status(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """등록 여부만 준다. 저장된 키 자체는 어떤 경우에도 응답에 싣지 않는다."""
    require_self(user_id, current_user_id)
    cur.execute("SELECT updated_at FROM user_partner_keys WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        return PartnerKeyStatus(registered=False)
    return PartnerKeyStatus(registered=True, updated_at=row[0])


@router.put("/{user_id}", response_model=PartnerKeyStatus)
def register(
    user_id: int,
    body: PartnerKeyIn,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")

    access_key = body.access_key.strip()
    secret_key = body.secret_key.strip()
    if not access_key or not secret_key:
        raise HTTPException(status_code=400, detail="키를 입력해주세요.")

    shopping_agent.save_user_coupang_key(cur, user_id, access_key, secret_key)
    cur.execute("SELECT updated_at FROM user_partner_keys WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return PartnerKeyStatus(registered=True, updated_at=row[0] if row else None)


@router.delete("/{user_id}", response_model=PartnerKeyStatus)
def unregister(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """연동을 해제한다. 이미 없어도 204가 아니라 같은 응답을 준다 - 화면 입장에서
    "지금 등록 안 된 상태"라는 결과는 같고, 있었는지 없었는지를 굳이 알릴 필요가 없다."""
    require_self(user_id, current_user_id)
    shopping_agent.delete_user_coupang_key(cur, user_id)
    return PartnerKeyStatus(registered=False)
