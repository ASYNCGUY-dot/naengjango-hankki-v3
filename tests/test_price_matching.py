"""KAMIS 품목 매칭과 가격용 조미료 판정을 검증한다 (2026-09-29).

재료비가 맞으려면 재료가 **올바른** KAMIS 품목·품종에 붙어야 한다. 틀린 품목에 붙으면
오류 없이 엉뚱한 금액이 나오고, 아무도 모른다. 그래서 실제로 겪은 경우를 하나씩 고정한다.

  - 대파를 찾으면 같은 "파" 아래의 쪽파가 아니라 대파 가격이어야 한다
  - 청양고추·삼겹살처럼 KAMIS에서 **품종**으로만 있는 재료도 찾아야 한다
  - 갈비처럼 돼지에도 소에도 있는 품종은 어느 쪽인지 모르므로 아무렇게나 고르면 안 된다
  - 양파는 조미료가 아니다 (부분 문자열 판정 때문에 "파"로 빠지고 있었다)

외부망을 타지 않는다. KAMIS 응답 모양을 흉내낸 목록으로 순수 함수만 부른다.
"""

import threading
import time

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


def test_a_leading_label_in_parentheses_is_not_the_ingredient():
    """"(속재료) 단호박"처럼 앞에 붙은 분류 표시는 떼고 본다.

    떼지 않으면 괄호 앞 품목 이름이 빈 문자열이 되고, 빈 문자열은 모든 품목 이름에 들어 있어서
    아무 품목에나 붙었다. 운영 레시피 43행이 전부 그랬다("(속재료) 홍시"가 풋고추 가격으로).
    """
    assert price_agent._base_and_hint("(속재료) 단호박") == ("단호박", "")
    assert price_agent._base_and_hint("(반죽재료)강력분") == ("강력분", "")
    assert price_agent.match_ingredient_price("(반죽재료) 강력분", ITEMS) is None
    assert price_agent.match_ingredient_price("(속재료) 양파", ITEMS)["item_name"] == "양파"


@pytest.mark.parametrize("raw, base", [
    ("재료 닭가슴살", "닭가슴살"),
    ("육수 다시마", "다시마"),
    ("양념 다진 마늘", "다진 마늘"),
    ("[주재료]닭다리살", "닭다리살"),
    ("[양념] 고추장", "고추장"),
    ("주재료 돼지고기(목살)", "돼지고기"),
])
def test_section_labels_in_front_are_dropped(raw, base):
    """원본 재료 텍스트를 나눌 때 "재료"·"육수"·"[주재료]" 같은 분류 표시가 이름 앞에 붙어 남았다.
    운영 레시피 176행이 이런 모양이고, 떼면 89행에 새로 가격이 붙는다(2026-10-01)."""
    assert price_agent._base_and_hint(raw)[0] == base


def test_a_label_word_alone_or_inside_a_name_is_kept():
    """분류어 하나만 있거나 이름 일부일 때는 떼지 않는다. "양념장"은 재료 이름 자체일 수 있다."""
    assert price_agent._base_and_hint("양념장")[0] == "양념장"
    assert price_agent._base_and_hint("재료")[0] == "재료"
    assert price_agent._base_and_hint("소스용토마토")[0] == "소스용토마토"


def test_labelled_seasoning_is_still_a_seasoning():
    """"양념 다진 마늘"은 다진 마늘이다. 분류어를 떼야 조미료로 빠지고, 안 떼면 "매칭 안 됨"으로 쌓인다."""
    assert price_agent.is_price_staple("양념 다진 마늘")


@pytest.mark.parametrize("name", ["(속재료)", "()", "", "  "])
def test_an_empty_name_matches_nothing(name):
    assert price_agent.match_ingredient_price(name, ITEMS) is None


# ---------- 부위·등급을 모를 때 (2026-10-01) ----------
#
# 레시피가 "쇠고기"라고만 쓰면 어느 부위·등급인지 모른다. 예전에는 KAMIS 응답에서 **첫 번째**
# 국산 품종을 썼는데, 소는 첫 번째가 안심 1등급이라 운영 레시피 55행이 소 품종 중앙값의
# 2.46배로 계산됐다. 응답 순서는 기준이 아니다. 같은 품목·같은 단위의 국산 후보 중 **가격이
# 가운데인 것**을 대표로 쓴다(짝수면 낮은 쪽).

BEEF = [
    _item("소", "안심", price=194780, category_code="500"),
    _item("소", "안심", price=159120, category_code="500"),
    _item("소", "양지", price=79170, category_code="500"),
    _item("소", "설도", price=45130, category_code="500"),
    _item("소", "설도", price=44370, category_code="500"),
]


def test_unnamed_cut_uses_the_middle_price_not_the_first_listed():
    m = price_agent.match_ingredient_price("쇠고기", BEEF)
    assert (price_agent._kind_base(m["kind_name"]), m["price"]) == ("양지", 79170)


def test_grades_of_a_named_cut_also_use_the_middle():
    """"소고기(안심)"처럼 부위를 알아도 등급(1++·1+·1)은 모른다. 가장 비싼 등급을 쓰지 않는다."""
    beef = BEEF + [_item("소", "안심", price=173350, category_code="500")]
    assert price_agent.match_ingredient_price("소고기(안심)", beef)["price"] == 173350
    assert price_agent.match_ingredient_price("안심", beef)["price"] == 173350


def test_even_number_of_candidates_takes_the_lower_middle():
    """돼지 품종 넷(갈비·앞다리·목심·삼겹살). 가운데 둘 중 낮은 쪽(앞다리)을 쓴다 - 매번 같은 답이 나와야 한다."""
    pork = [
        _item("돼지", "삼겹살", price=30660, category_code="500"),
        _item("돼지", "앞다리", price=16960, category_code="500"),
        _item("돼지", "목심", price=28710, category_code="500"),
        _item("돼지", "갈비", price=16800, category_code="500"),
    ]
    m = price_agent.match_ingredient_price("돼지고기", pork)
    assert price_agent._kind_base(m["kind_name"]) == "앞다리"


def test_imported_kind_inside_a_domestic_item_is_not_counted_as_domestic():
    """땅콩·고등어는 품목 이름이 아니라 **품종** 이름에 "수입"을 적는다. 국산이 있으면 국산을 쓴다."""
    peanuts = [
        _item("땅콩", "수입", price=9000, category_code="300"),
        _item("땅콩", "국산", price=30000, category_code="300"),
    ]
    assert price_agent._kind_base(price_agent.match_ingredient_price("땅콩", peanuts)["kind_name"]) == "국산"


def test_different_units_are_not_compared_by_price():
    """계란 30구 6,882원과 10구 4,209원은 값을 바로 비교할 수 없다. 첫 후보의 단위 안에서만 고른다.

    30구를 앞에 둔다. 단위를 무시하고 값만 비교하면 싼 10구가 골라져서 드러난다.
    """
    eggs = [
        _item("계란", "특란30구", price=6882, unit="30구", category_code="500"),
        _item("계란", "특란10구", price=4209, unit="10구", category_code="500"),
    ]
    assert price_agent.match_ingredient_price("계란", eggs)["unit"] == "30구"


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


def test_categories_are_fetched_at_the_same_time(monkeypatch):
    """6부류를 순서대로 부르면 배포 서버에서 재료비 카드가 11초 넘게 걸렸다(2026-10-01 스모크).

    6개 요청이 모두 도착해야 풀리는 장벽을 세운다. 하나씩 부르면 첫 요청이 장벽에서
    시간 초과로 깨진다.
    """
    barrier = threading.Barrier(len(price_agent.CATEGORY_CODES), timeout=5)

    class FakeResponse:
        def json(self):
            return {"data": {"error_code": "000", "item": []}}

    def fake_get(url, params=None, timeout=None):
        barrier.wait()
        return FakeResponse()

    monkeypatch.setattr(price_agent.requests, "get", fake_get)
    price_agent.get_all_prices()


def test_parallel_fetch_keeps_category_order(monkeypatch):
    """응답이 도착한 순서가 아니라 부류 순서대로 합친다. 품목 순서가 매칭의 동점 처리에 쓰여서,
    호출마다 순서가 바뀌면 같은 레시피의 재료비가 요청마다 달라질 수 있다."""
    delays = {"100": 0.3, "200": 0.0, "300": 0.2, "400": 0.1, "500": 0.25, "600": 0.05}

    class FakeResponse:
        def __init__(self, code):
            self.code = code

        def json(self):
            return {"data": {"error_code": "000", "item": [
                {"item_name": f"품목{self.code}", "kind_name": "", "unit": "1kg", "dpr1": "1,000"},
            ]}}

    def fake_get(url, params=None, timeout=None):
        code = params["p_item_category_code"]
        time.sleep(delays[code])
        return FakeResponse(code)

    monkeypatch.setattr(price_agent.requests, "get", fake_get)
    items = price_agent.get_all_prices()
    assert [i["category_code"] for i in items] == list(price_agent.CATEGORY_CODES)


# ---------- 단위 (2026-10-01) ----------
#
# 조회에 p_convert_kg_yn=Y를 쓴다. 이때 KAMIS는 무게 단위 품목의 **가격만 1kg당으로 바꾸고
# unit은 원래 값("100g")으로 둔다.** 같은 날 Y와 N을 나란히 받아 확인했다 - 풋고추는 unit=100g에
# Y 17,756원 / N 1,776원, 깻잎은 unit=50g에 Y 31,556원 / N 1,578원. 가격 있는 소매 품목 177개
# 전부가 "무게 단위면 Y는 1kg당, 개수 단위면 그대로" 규칙에 맞았다. unit을 그대로 믿고 나누면
# 100g 품목은 10배, 깻잎은 20배 비싸게, 쌀 20kg은 20배 싸게 나온다.

def _kamis_response(*items):
    class FakeResponse:
        def json(self):
            return {"data": {"error_code": "000", "item": list(items)}}
    return FakeResponse()


@pytest.mark.parametrize("unit, price_text", [
    ("100g", "17,756"),   # 풋고추
    ("50g", "31,556"),    # 깻잎
    ("600g", "30,767"),   # 건고추
    ("20kg", "3,000"),    # 쌀 (kg당으로 내려온 값)
    ("1kg", "1,986"),     # 양파
])
def test_weight_units_are_priced_per_kg(monkeypatch, unit, price_text):
    """Y로 받은 무게 단위 가격은 원래 unit과 상관없이 1kg당이다. 저장할 때 unit을 그에 맞춘다."""
    monkeypatch.setattr(price_agent.requests, "get", lambda *a, **k: _kamis_response(
        {"item_name": "품목", "kind_name": "품종(1kg)", "unit": unit, "dpr1": price_text},
    ))
    item = price_agent.fetch_category_prices("200")[0]
    assert item["unit"] == "1kg"
    assert item["price"] == float(price_text.replace(",", ""))


@pytest.mark.parametrize("unit", ["1개", "10구", "1마리", "1포기", "10장", "1L"])
def test_count_units_keep_their_own_unit(monkeypatch, unit):
    """개수 단위는 Y여도 바뀌지 않는다(파프리카 1개, 계란 10구가 Y와 N에서 같은 값)."""
    monkeypatch.setattr(price_agent.requests, "get", lambda *a, **k: _kamis_response(
        {"item_name": "품목", "kind_name": "품종", "unit": unit, "dpr1": "2,061"},
    ))
    assert price_agent.fetch_category_prices("200")[0]["unit"] == unit


def test_chili_sold_per_100g_costs_what_the_shop_charges(monkeypatch):
    """청양고추 10g. 100g에 1,284원이면 약 128원이어야 한다(고치기 전에는 1,284원으로 나왔다)."""
    monkeypatch.setattr(price_agent.requests, "get", lambda *a, **k: _kamis_response(
        {"item_name": "풋고추", "kind_name": "청양고추(1kg)", "unit": "100g", "dpr1": "12,844"},
    ))
    items = price_agent.fetch_category_prices("200")
    result = price_agent.estimate_recipe_total_cost(
        [{"name": "청양고추", "amount": 10, "unit": "g"}], items,
    )
    assert result["total_cost"] == pytest.approx(128.44)


def test_zero_price_is_treated_as_missing():
    """닭 절단육이 당일 0원으로 와서 닭 재료비가 0원으로 나왔다. 0은 값이 없는 것으로 본다."""
    item = {"dpr1": "0", "day1": "당일 (10/01)", "dpr2": "5,456", "day2": "1일전 (09/30)"}
    assert price_agent._extract_price_and_day(item) == (5456.0, "1일전 (09/30)")
    assert price_agent._extract_price_and_day({"dpr1": "0", "dpr2": "0"}) == (None, None)


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
