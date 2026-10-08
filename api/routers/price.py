"""
V1의 price_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
KAMIS 서울 소매가격(2026-09-29까지는 도매)을 가져와 레시피의 가격 등급(estimate_recipe_price_tier)과
재료비 추정(estimate_recipe_total_cost)을 그대로 노출한다.

2026-07-18 3단 비교 카드 UI 검증 중 발견: KAMIS 공공 API가 가끔 부류 하나에 대해
정상 dict 대신 list를 내려줘서(추정: 순간적인 요청 제한/오류 응답), price_agent.py의
fetch_category_prices()가 그 shape을 가정하고 .get()을 호출하다 AttributeError로 죽는다.
safety.py에서 식약처 API 무응답을 503으로 감싼 것과 같은 원칙 - agent 파일은 그대로 두고
이 라우터 계층에서만 예외를 잡아 "일시적으로 응답하지 않음" 503으로 바꾼다.

2026-10-04 원인 확인: 위의 "가끔 list"는 요청 제한이 아니라 **자료가 없는 날**이었다. 일요일을
조회 날짜로 넣으면 {"data": ["001"]}이 온다(7월 18·19일도 토·일요일이다). price_agent가 이제
하루씩 거슬러 올라가 조회하므로 그 경우는 여기까지 오지 않는다. 아래 예외 처리는 그 밖의
예상 못 한 응답 모양에 대비해 그대로 둔다.

2026-07-19 추가: KAMIS는 부류(채소/곡물/축산/수산) 4개를 매 요청마다 순차 호출해서
느리고, 그만큼 실패할 기회도 4배다. get_all_prices() 결과를 TTLCache로 10분간
재사용해서 호출 빈도를 줄이고, 방금 실패해도 직전 성공 응답이 있으면 그대로 돌려준다
(safety.py와 동일한 원칙, api/ttl_cache.py 참고).
"""

import sqlite3
from collections import Counter

import requests
from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from api.ttl_cache import TTLCache
from src.agents import portion_agent, price_agent, recommendation_agent

router = APIRouter(prefix="/recommendation/recipes", tags=["price"])

_prices_cache = TTLCache(ttl_seconds=600)


class MatchedIngredient(BaseModel):
    ingredient: str
    item_name: str
    unit: str
    price: float
    ratio: float | None


class IncludedCost(BaseModel):
    ingredient: str
    matched_name: str
    amount_g: float
    cost: float
    is_estimated: bool
    # 어느 날 시세인지. "당일 (09/30)" / "1주일전 (09/23)" 같은 KAMIS 라벨 그대로.
    price_day: str | None = None


class ExcludedCost(BaseModel):
    ingredient: str
    reason: str


class PriceBasis(BaseModel):
    """화면이 밝혀야 하는 시세의 출처와 기준. 화면이 지어내지 않도록 서버가 정해서 준다."""

    provider: str
    market: str
    # 재료비에 들어간 가격의 날짜 라벨. 많이 쓰인 순. 여럿이면 일부는 더 이전 시세라는 뜻이다.
    price_days: list[str]


class PriceResponse(BaseModel):
    tier: str
    matched: list[MatchedIngredient]
    unmatched: list[str]
    total_cost: float
    included: list[IncludedCost]
    excluded: list[ExcludedCost]
    # 재료비를 몇 인분으로 환산했는지. 프로필의 가구원 수다.
    household_size: int
    basis: PriceBasis


@router.get("/{recipe_id}/price", response_model=PriceResponse)
def get_recipe_price(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    profile = recommendation_agent.get_user_profile(cur, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")

    cur.execute("SELECT id FROM recipes WHERE id = ?", (recipe_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")

    try:
        household_size = int(profile.get("household_size") or 1)
    except (TypeError, ValueError):
        household_size = 1

    base_servings, items = portion_agent.get_recipe_ingredients(cur, recipe_id)
    # 구획 제목("주재료")과 안내 문구("1인분 기준")는 재료가 아니다. 거르지 않으면 재료비 카드의
    # "시세를 못 찾은 재료"에 재료처럼 나온다. 상세 화면과 같은 판정을 쓴다.
    items = [
        item for item in items
        if portion_agent.classify_ingredient_row(item["name"], item["amount"]) == "ingredient"
    ]
    if not items:
        raise HTTPException(status_code=404, detail="이 레시피에는 재료 수량 정보가 없습니다.")

    scaled_items = portion_agent.scale_ingredients(items, base_servings, household_size)
    ingredient_names = [item["name"] for item in items]

    unavailable = HTTPException(
        status_code=503,
        detail="KAMIS 가격 정보 서비스가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해주세요.",
    )
    try:
        all_items = _prices_cache.get_or_fetch(price_agent.get_all_prices)
    except price_agent.PartialPricesError as partial:
        # 부류 일부만 받았다. 직전의 온전한 결과가 있었다면 캐시가 그것을 돌려줬을 테니, 여기
        # 왔다는 건 그것도 없다는 뜻이다. 받은 일부로 응답하되 캐시하지 않는다 - 다음 요청이
        # 바로 다시 시도한다. 빠진 부류의 재료는 화면에 "가격 정보 없음"으로 나온다.
        if not partial.items:
            raise unavailable
        all_items = partial.items
    except (requests.RequestException, AttributeError, ValueError, TypeError):
        raise unavailable
    tier_result = price_agent.estimate_recipe_price_tier(ingredient_names, all_items)
    cost_result = price_agent.estimate_recipe_total_cost(scaled_items, all_items)

    days = Counter(i["price_day"] for i in cost_result["included"] if i.get("price_day"))
    basis = PriceBasis(
        provider="KAMIS 농산물유통정보(aT)",
        market="서울 소매가",
        price_days=[day for day, _ in days.most_common()],
    )

    return PriceResponse(
        tier=tier_result["tier"],
        matched=tier_result["matched"],
        unmatched=tier_result["unmatched"],
        total_cost=cost_result["total_cost"],
        included=cost_result["included"],
        excluded=cost_result["excluded"],
        household_size=household_size,
        basis=basis,
    )
