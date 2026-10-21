"""
V1의 price_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
KAMIS 서울 소매가격(2026-09-29까지는 도매)을 가져와 레시피의 재료비 추정(estimate_recipe_total_cost)을
그대로 노출한다. 가격 등급(tier·matched·unmatched)은 2026-10-20에 응답에서 뺐다 - 화면이 10월 9일부터
그리지 않았고, 실제 재료비와 거의 무관한 값이었다(PROJECT_REPORT_V3.md §4.5).

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
(safety.py와 동일한 원칙, api/ttl_cache.py 참고). 2026-10-18부터 그 직전 응답은 받은 지
24시간 안의 것만 쓰고, 썼다는 것을 응답(basis.stale)으로 밝힌다.
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

# 10분 동안은 받은 시세를 그대로 다시 쓴다. 갱신에 실패하면 이전에 받은 시세를 **24시간까지만**
# 쓴다(2026-10-18 결정). KAMIS 시세는 하루 단위로 바뀌어서, 그보다 오래 붙잡으면 날짜가 밝혀져
# 있어도 "지금 시세"로 읽힌다. 시세 날짜 자체는 품목마다 price_day로 따로 밝히고, 조회는 최대
# 7일까지만 거슬러 올라간다(price_agent.MAX_LOOKBACK_DAYS).
KAMIS_MAX_STALE_SECONDS = 24 * 60 * 60
_prices_cache = TTLCache(ttl_seconds=600, max_stale_seconds=KAMIS_MAX_STALE_SECONDS)


class IncludedCost(BaseModel):
    ingredient: str
    matched_name: str
    # 어느 품종·단위·단가로 계산했는지 (2026-10-17). 계산을 되짚을 수 있게 싣는다.
    matched_kind: str | None = None
    unit: str
    unit_price: float
    # 이 가격이 재료와 어떤 관계인지. exact(같은 품목·품종) 또는 representative(부위·품종을 안
    # 적어 같은 품목의 가운데 값). 다른 부위·상태의 시세는 합계에 넣지 않고 excluded로 보낸다.
    match_basis: str
    amount_g: float
    cost: float
    # 개수 단위를 평균 무게로 바꾼 값인지. match_basis와 다른 뜻이다(섞지 않는다).
    is_estimated: bool
    # 어느 날 시세인지. "09/30"처럼 날짜만 준다. KAMIS 라벨의 "1일전" 같은 말은 조회한 날짜
    # 기준이라, 연휴에 거슬러 올라가 조회하면 틀린 말이 된다(price_agent._price_date).
    price_day: str | None = None


class ExcludedCost(BaseModel):
    ingredient: str
    reason: str
    # 왜 뺐는지: no_amount(양이 g로 안 적힘)·no_match(KAMIS에 없음)·unit(단위 환산 불가)·
    # other_cut(정확한 부위·품종 시세 없음)·other_state(상태가 다른 품목 시세뿐). 화면이 이유별로 안내한다.
    reason_code: str


class PriceBasis(BaseModel):
    """화면이 밝혀야 하는 시세의 출처와 기준. 화면이 지어내지 않도록 서버가 정해서 준다."""

    provider: str
    market: str
    # 재료비에 들어간 가격의 날짜("10/08"). 많이 쓰인 순. 여럿이면 날짜가 섞여 있다는 뜻이다 -
    # 앞의 것이 가장 최근이라는 뜻은 아니다.
    price_days: list[str]
    # 이번 조회가 실패해서 이전에 받아 둔 시세(받은 지 24시간 안)로 계산했는지 (2026-10-18).
    stale: bool = False
    # 이번 조회에서 부류 일부를 못 받았고 쓸 만한 이전 결과도 없어 받은 것만으로 계산했는지.
    # 이때는 못 받은 부류의 재료가 "KAMIS에 없음"과 똑같이 빠진다.
    partial: bool = False


class PriceResponse(BaseModel):
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

    try:
        household_size = int(profile.get("household_size") or 1)
    except (TypeError, ValueError):
        household_size = 1

    return _price_response(cur, recipe_id, household_size)


# "/{recipe_id}/price/public"은 위 경로와 겹치지 않는다(뒤에 "/public"이 더 붙는다).
@router.get("/{recipe_id}/price/public", response_model=PriceResponse)
def get_recipe_price_public(recipe_id: int, cur: sqlite3.Cursor = Depends(get_db)):
    """로그인 없이 이 레시피의 1인분 재료비를 본다 (2026-10-21).

    재료비가 로그인 뒤에만 있어서, 레시피 링크를 받은 사람(공모전 심사자 포함)은 이 서비스의
    핵심인 KAMIS 재료비를 볼 수 없었다. 레시피 상세(/recommendation/recipes/{id})가 이미
    로그인 없이 열려 있으니 그와 같은 범위로 연다.

    개인화는 하지 않는다. 가구원 수는 프로필에 있어서 **항상 1인분**으로 계산한다. 공개
    경로라 사용자 데이터는 읽지도 쓰지도 않는다. KAMIS 호출은 로그인 경로와 같은 캐시(10분)를
    거쳐서, 이 경로가 많이 불려도 KAMIS 호출 수는 늘지 않는다.
    """
    return _price_response(cur, recipe_id, household_size=1)


def _price_response(cur: sqlite3.Cursor, recipe_id: int, household_size: int) -> PriceResponse:
    cur.execute("SELECT id FROM recipes WHERE id = ?", (recipe_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")

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

    unavailable = HTTPException(
        status_code=503,
        detail="KAMIS 가격 정보 서비스가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해주세요.",
    )
    partial = False
    try:
        all_items, stale = _prices_cache.get_or_fetch_with_status(price_agent.get_all_prices)
    except price_agent.PartialPricesError as error:
        # 부류 일부만 받았다. 24시간 안의 온전한 결과가 있었다면 캐시가 그것을 돌려줬을 테니, 여기
        # 왔다는 건 그것도 없다는 뜻이다. 받은 일부로 응답하되 캐시하지 않는다 - 다음 요청이
        # 바로 다시 시도한다. 빠진 부류의 재료는 화면에 "가격 정보 없음"으로 나온다.
        if not error.items:
            raise unavailable
        all_items, stale, partial = error.items, False, True
    except (requests.RequestException, AttributeError, ValueError, TypeError):
        raise unavailable
    cost_result = price_agent.estimate_recipe_total_cost(scaled_items, all_items)

    days = Counter(i["price_day"] for i in cost_result["included"] if i.get("price_day"))
    basis = PriceBasis(
        provider="KAMIS 농산물유통정보(aT)",
        market="서울 소매가",
        price_days=[day for day, _ in days.most_common()],
        stale=stale,
        partial=partial,
    )

    return PriceResponse(
        total_cost=cost_result["total_cost"],
        included=cost_result["included"],
        excluded=cost_result["excluded"],
        household_size=household_size,
        basis=basis,
    )
