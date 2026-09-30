"""KAMIS 품목 매칭과 가격용 조미료 판정을 검증한다 (2026-09-29).

재료비가 맞으려면 재료가 **올바른** KAMIS 품목·품종에 붙어야 한다. 틀린 품목에 붙으면
오류 없이 엉뚱한 금액이 나오고, 아무도 모른다. 그래서 실제로 겪은 경우를 하나씩 고정한다.

  - 대파를 찾으면 같은 "파" 아래의 쪽파가 아니라 대파 가격이어야 한다
  - 청양고추·삼겹살처럼 KAMIS에서 **품종**으로만 있는 재료도 찾아야 한다
  - 갈비처럼 돼지에도 소에도 있는 품종은 어느 쪽인지 모르므로 아무렇게나 고르면 안 된다
  - 양파는 조미료가 아니다 (부분 문자열 판정 때문에 "파"로 빠지고 있었다)

외부망을 타지 않는다. KAMIS 응답 모양을 흉내낸 목록으로 순수 함수만 부른다.
"""

import pytest

from src.agents import price_agent


def _item(item_name, kind_name, price=1000, unit="1kg", category_code="200"):
    return {
        "item_name": item_name, "kind_name": kind_name, "unit": unit, "price": price,
        "category_code": category_code, "category_name": "채소류",
    }


# 실제 KAMIS 소매 응답의 품목·품종 이름을 그대로 옮겼다(2026-09-29 조회). 순서도 일부러
# 헷갈리게 둔다 - 쪽파를 대파보다 앞에 두면 "첫 번째 것"을 집는 코드가 드러난다.
ITEMS = [
    _item("파", "쪽파(1kg)", price=9000),
    _item("파", "대파(1kg)", price=3000),
    _item("풋고추", "꽈리고추(1kg)", price=1500, unit="100g"),
    _item("풋고추", "청양고추(1kg)", price=1200, unit="100g"),
    _item("붉은고추", "붉은고추(1kg)", price=1800, unit="100g"),
    _item("돼지", "갈비", price=18000, category_code="500"),
    _item("돼지", "목심", price=21000, category_code="500"),
    _item("돼지", "삼겹살", price=26000, category_code="500"),
    _item("소", "갈비", price=60000, category_code="500"),
    _item("소", "등심", price=95000, category_code="500"),
    _item("닭", "육계(kg)", price=6000, category_code="500"),
    _item("계란", "특란10구", price=4000, unit="10구", category_code="500"),
    _item("우유", "흰우유", price=2800, unit="1L", category_code="500"),
    _item("수입 돼지고기", "삼겹살", price=12000, category_code="500"),
    _item("콩", "흰콩(국산)(500g)", price=6000, unit="500g", category_code="100"),
    _item("양파", "양파(1kg)", price=2500),
]


def _match(name):
    m = price_agent.match_ingredient_price(name, ITEMS)
    return (m["item_name"], price_agent._kind_base(m.get("kind_name"))) if m else None


# ---------- 품종으로 찾기 ----------

def test_leek_gets_the_leek_price_not_chives():
    """대파는 대파 가격이어야 한다. 품목 이름("파")만 보면 앞에 있는 쪽파를 집는다."""
    assert _match("대파") == ("파", "대파")
    assert _match("쪽파") == ("파", "쪽파")


def test_ingredients_that_exist_only_as_a_kind_are_found():
    """청양고추와 삼겹살은 KAMIS에 품목이 아니라 품종으로만 있다."""
    assert _match("청양고추") == ("풋고추", "청양고추")
    assert _match("삼겹살") == ("돼지", "삼겹살")


def test_domestic_and_imported_of_the_same_kind_are_not_ambiguous():
    """"돼지"와 "수입 돼지고기"가 둘 다 삼겹살을 갖는다. 이걸 모호하다고 보면 삼겹살이 안 붙는다.

    처음 짠 규칙이 실제로 그랬다 - 테스트를 쓰다가 실제 KAMIS 목록에 수입 품목이 있는 것을
    보고 알았다. 국산을 고른다.
    """
    m = price_agent.match_ingredient_price("삼겹살", ITEMS)
    assert m["item_name"] == "돼지"
    assert m["price"] == 26000


def test_a_kind_shared_by_two_items_is_not_guessed():
    """갈비는 돼지에도 소에도 있다. 어느 쪽인지 모르면서 하나를 고르면 세 배 넘게 틀린다."""
    assert _match("갈비") is None


def test_a_hint_in_parentheses_picks_the_kind_inside_that_item():
    """레시피에는 "돼지고기(삼겹살)"이나 파싱 때 괄호가 잘린 "소고기(등심" 같은 이름이 있다."""
    assert _match("돼지고기(삼겹살)") == ("돼지", "삼겹살")
    assert _match("소고기(등심") == ("소", "등심")
    # 힌트가 품목 안에 없으면 품목 자체로는 여전히 붙는다.
    assert _match("돼지고기(다짐육)")[0] == "돼지"


# ---------- 이름만 다른 것 ----------

@pytest.mark.parametrize(
    "ingredient,item",
    [("달걀", "계란"), ("홍고추", "붉은고추"), ("청고추", "풋고추"), ("닭가슴살", "닭"), ("닭고기", "닭")],
)
def test_synonyms_from_the_data(ingredient, item):
    assert _match(ingredient)[0] == item


def test_bean_sprouts_do_not_match_beans():
    """방향 규칙 회귀 방지: 품목 "콩"이 "콩나물" 안에 들어 있다고 붙으면 안 된다."""
    assert _match("콩나물") is None


# ---------- 가격용 조미료 판정 ----------

@pytest.mark.parametrize("name", ["양파", "파프리카", "파인애플", "파슬리", "깐마늘쫑"])
def test_real_ingredients_that_merely_contain_a_seasoning_are_kept(name):
    """부분 문자열로 판정하면 이것들이 전부 조미료("파"·"마늘")로 빠진다. 실제로 그랬다."""
    assert not price_agent.is_price_staple(name)


@pytest.mark.parametrize("name", ["대파", "파", "소금", "간장", "다진마늘", "다진 마늘", "후춧가루", "올리브유"])
def test_seasonings_are_left_out_of_the_price(name):
    assert price_agent.is_price_staple(name)


def test_tier_ignores_seasonings_instead_of_counting_them_as_unmatched():
    """조미료가 "매칭 안 됨"으로 쌓이면 매칭 비율이 깎여 멀쩡한 레시피가 "정보부족"이 된다.

    라우터는 재료 전체를 넘긴다. 예전에는 "부르기 전에 걸렀다고 가정"했는데 아무도 안 거르고 있었다.
    """
    names = ["양파", "청양고추", "달걀", "소금", "간장", "설탕", "참기름", "후춧가루", "식용유"]
    result = price_agent.estimate_recipe_price_tier(names, ITEMS)
    assert result["tier"] != "정보부족"
    assert "소금" not in result["unmatched"]


# ---------- 단위 ----------

def test_egg_and_milk_units_convert_as_estimates():
    assert price_agent._kamis_unit_to_grams("10구", "계란") == (600, True)
    assert price_agent._kamis_unit_to_grams("1L", "우유") == (1000, True)
    # g·kg는 추정이 아니다.
    assert price_agent._kamis_unit_to_grams("100g", "풋고추") == (100, False)


def test_total_cost_uses_the_matched_kind_price():
    """재료비가 품종 가격으로 계산되는지 끝까지 본다. 대파 100g = 3000원/kg x 0.1 = 300원."""
    result = price_agent.estimate_recipe_total_cost(
        [{"name": "대파", "amount": 100, "unit": "g"}, {"name": "양파", "amount": 200, "unit": "g"}],
        ITEMS,
    )
    # 대파는 조미료라 빠지고, 양파만 들어간다: 2500원/kg x 0.2 = 500원.
    assert result["total_cost"] == pytest.approx(500)
    assert [i["ingredient"] for i in result["included"]] == ["양파"]


# ---------- 조회 ----------

def test_fetch_asks_for_retail_prices_in_every_category(monkeypatch):
    """소매가를 6개 부류 모두에서 받는지. 도매나 4부류로 되돌아가면 재료비가 흔들린다."""
    seen = []

    class FakeResponse:
        def json(self):
            return {"data": {"error_code": "000", "item": []}}

    def fake_get(url, params=None, timeout=None):
        seen.append(params)
        return FakeResponse()

    monkeypatch.setattr(price_agent.requests, "get", fake_get)
    price_agent.get_all_prices()

    assert {p["p_item_category_code"] for p in seen} == {"100", "200", "300", "400", "500", "600"}
    assert {p["p_product_cls_code"] for p in seen} == {"01"}


def test_fetch_keeps_the_kind_name(monkeypatch):
    class FakeResponse:
        def json(self):
            return {"data": {"error_code": "000", "item": [
                {"item_name": "파", "kind_name": "대파(1kg)", "unit": "1kg", "dpr1": "3,000"},
            ]}}

    monkeypatch.setattr(price_agent.requests, "get", lambda *a, **k: FakeResponse())
    items = price_agent.fetch_category_prices("200")
    assert items[0]["kind_name"] == "대파(1kg)"
    assert items[0]["price"] == 3000.0


# ---------- 시세 날짜 ----------

def test_price_comes_with_the_day_it_was_recorded():
    """당일 값이 없으면 1일 전, 1주일 전 순으로 내려가고, 어느 날 값인지 함께 준다."""
    item = {"dpr1": "-", "day1": "당일 (09/30)", "dpr2": "-", "day2": "1일전 (09/29)",
            "dpr3": "3,100", "day3": "1주일전 (09/23)"}
    assert price_agent._extract_price_and_day(item) == (3100.0, "1주일전 (09/23)")


def test_prices_older_than_two_weeks_are_never_used():
    """dpr5는 1개월 전, dpr6은 1년 전이다(KAMIS 응답 라벨로 확인). 오늘 재료비로 쓰면 안 된다."""
    item = {"dpr1": "-", "dpr2": "-", "dpr3": "-", "dpr4": "-",
            "dpr5": "2,900", "day5": "1개월전", "dpr6": "2,500", "day6": "1년전"}
    assert price_agent._extract_price_and_day(item) == (None, None)
