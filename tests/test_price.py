"""
/recommendation/recipes/{id}/price를 검증한다.

이번 세션에 발견한 실제 버그의 회귀 테스트가 핵심이다: KAMIS 공공 API가 가끔 dict 대신
list를 내려줘서 price_agent.get_all_prices()가 AttributeError로 죽는 문제가 있었고,
safety.py와 같은 원칙으로 라우터 계층에서 503으로 감싸도록 고쳤다(api/routers/price.py).
KAMIS는 실제 외부망 호출이라 테스트에서는 price_agent.get_all_prices를 monkeypatch로
대체해서, 매번 진짜 API를 타지 않고도 정상 응답/예외 두 경로를 모두 재현한다.

2026-07-19 추가: api/routers/price.py가 get_all_prices() 결과를 TTLCache로 10분간
재사용하도록 바뀌어서, 그 캐시(_prices_cache)가 모듈 전역 상태로 남는다 - safety
테스트와 같은 이유로, 매 테스트 전에 캐시를 비워서 monkeypatch 응답이 실제로 타게 한다.
"""

import pytest
import requests

from api.routers import price as price_router
from src.agents import price_agent

RECIPE_ID = 1  # seed.sql "두부조림" (재료: 두부 200g, 양파 50g)
RECIPE_WITHOUT_INGREDIENTS_ID = 2

FAKE_KAMIS_ITEMS = [
    {"item_name": "두부", "unit": "1kg", "price": 2000, "category_code": "200", "category_name": "채소류"},
    {"item_name": "양파", "unit": "1kg", "price": 1500, "category_code": "200", "category_name": "채소류"},
]


@pytest.fixture(autouse=True)
def _reset_prices_cache():
    price_router._prices_cache.clear()
    yield


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _signup_with_household_size_2(client, username: str) -> tuple[int, dict]:
    # base_servings=2인 시드 레시피와 배율을 1로 맞춰서(household_size/base_servings=1),
    # 환산 없이 원본 수량(두부 200g)이 그대로 나오게 한다 - 프로필을 안 채우면
    # household_size가 기본값 1로 떨어져 배율이 0.5가 되므로, 원가 계산 테스트에서는
    # 명시적으로 채워야 한다.
    user_id, headers = _signup(client, username)
    client.put(f"/profile/{user_id}", json={
        "gender": "여성", "age_group": "30대", "allergy": "", "health_goal": "체중감량",
        "purpose": "테스트", "cooking_level": "초급", "supplements": "", "household_size": 2,
        "novelty_pref": "", "cooking_tools": "", "medical_conditions": "",
    }, headers=headers)
    return user_id, headers


def test_price_without_token_returns_401(client):
    res = client.get(f"/recommendation/recipes/{RECIPE_ID}/price", params={"user_id": 999999999})
    assert res.status_code == 401


def test_price_nonexistent_recipe_returns_404(client, monkeypatch):
    monkeypatch.setattr(price_agent, "get_all_prices", lambda: FAKE_KAMIS_ITEMS)
    user_id, headers = _signup(client, "u_price_1")
    res = client.get("/recommendation/recipes/999999/price", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 404


def test_price_recipe_without_ingredients_returns_404(client, monkeypatch):
    monkeypatch.setattr(price_agent, "get_all_prices", lambda: FAKE_KAMIS_ITEMS)
    user_id, headers = _signup(client, "u_price_2")
    res = client.get(
        f"/recommendation/recipes/{RECIPE_WITHOUT_INGREDIENTS_ID}/price",
        params={"user_id": user_id}, headers=headers,
    )
    assert res.status_code == 404
    assert "재료 수량 정보가 없습니다" in res.json()["detail"]


def test_price_happy_path_returns_cost_breakdown(client, monkeypatch):
    monkeypatch.setattr(price_agent, "get_all_prices", lambda: FAKE_KAMIS_ITEMS)
    user_id, headers = _signup_with_household_size_2(client, "u_price_3")

    res = client.get(f"/recommendation/recipes/{RECIPE_ID}/price", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    # 재료가 2개뿐이라 estimate_recipe_price_tier()의 "최소 3개 매칭" 기준에 못 미쳐
    # tier는 "정보부족"이 정상이다 - 이 테스트는 tier 산정 로직이 아니라 라우터가 응답을
    # 제대로 조립하는지(모든 필드가 채워지는지)를 확인한다.
    assert body["tier"] == "정보부족"
    # "양파"는 recommendation_agent.is_staple()이 "파"(대파/파와 같은 조미료)의 부분
    # 문자열로 걸러내는 재료라서(실제로 확인함), estimate_recipe_total_cost()의 원가
    # 계산에서는 아예 빠지고 "두부"만 포함된다 - tier 산정(ingredient_names 기준)과는
    # 다른 규칙이다.
    assert body["total_cost"] == 400.0
    assert len(body["included"]) == 1
    assert body["included"][0]["ingredient"] == "두부"


def test_price_returns_503_when_kamis_response_is_malformed(client, monkeypatch):
    # 실제로 겪은 버그를 그대로 재현한다: KAMIS가 dict 대신 list를 내려주면
    # fetch_category_prices() 안에서 data.get(...)이 AttributeError를 던진다.
    def _raise():
        raise AttributeError("'list' object has no attribute 'get'")

    monkeypatch.setattr(price_agent, "get_all_prices", _raise)
    user_id, headers = _signup(client, "u_price_4")

    res = client.get(f"/recommendation/recipes/{RECIPE_ID}/price", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 503
    assert "KAMIS" in res.json()["detail"]


def test_price_returns_503_when_kamis_times_out(client, monkeypatch):
    def _raise():
        raise requests.exceptions.ReadTimeout("simulated KAMIS timeout")

    monkeypatch.setattr(price_agent, "get_all_prices", _raise)
    user_id, headers = _signup(client, "u_price_5")

    res = client.get(f"/recommendation/recipes/{RECIPE_ID}/price", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 503


def test_price_reuses_cached_kamis_response_within_ttl(client, monkeypatch):
    call_count = {"n": 0}

    def _fake_prices():
        call_count["n"] += 1
        return FAKE_KAMIS_ITEMS

    monkeypatch.setattr(price_agent, "get_all_prices", _fake_prices)
    user_id, headers = _signup_with_household_size_2(client, "u_price_6")

    client.get(f"/recommendation/recipes/{RECIPE_ID}/price", params={"user_id": user_id}, headers=headers)
    client.get(f"/recommendation/recipes/{RECIPE_ID}/price", params={"user_id": user_id}, headers=headers)
    # KAMIS는 부류 4개를 매번 순회하는 느린 호출이라, 캐시가 안 먹으면 여기서 4번씩
    # 두 배로 늘어난다 - 두 번째 요청은 캐시를 그대로 써서 fetch 자체가 1번만 일어난다.
    assert call_count["n"] == 1
