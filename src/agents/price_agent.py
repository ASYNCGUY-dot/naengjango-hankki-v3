"""
Price Agent [선택] - 가격대별 메뉴 등급 + 재료비 총액 추정
- KAMIS(농산물유통정보) API로 채소류(200)/식량작물(곡물,100)/축산물(500)/수산물(600) 4개 부류의
  도매가격을 가져와서, 레시피 재료가 각 부류 안에서 상대적으로 비싼 편인지 싼 편인지를 비교한다
  (estimate_recipe_price_tier). 이건 절대 금액을 합산하지 않고 "중앙값 대비 몇 배인지"로만 등급을 매긴다.
- 추가로 estimate_recipe_total_cost()는 "이 레시피를 만드는 데 대략 얼마 드는지"를 원 단위로 추정한다.
  재료마다 KAMIS 단위가 제각각이라(kg/g/개/단 등), g 단위로 정확히 환산되는 재료만 계산에 포함하고,
  "개"처럼 개수 단위인 재료는 AVG_PIECE_WEIGHT_G(품목별 평균 중량표)로 추정 환산한다. 매칭이 안 되거나
  단위 환산이 안 되는 재료는 계산에서 빠지므로, 결과는 "포함된 재료만의 부분 합계"다.
- 두부처럼 가공식품인 재료는 KAMIS가 다루는 범위(농·축·수산물) 밖이라 매칭되지 않는다 (정보부족으로 표시).
- 지침 8번 원칙: 가격 정보는 참고용이며, 최신 정보는 공식 채널(KAMIS 등)에서 재확인을 권장한다.
"""

import os
import re
import statistics
import requests
from datetime import date
from dotenv import load_dotenv

from recommendation_agent import is_staple

load_dotenv()
CERT_KEY = os.getenv("KAMIS_CERT_KEY")
CERT_ID = os.getenv("KAMIS_CERT_ID")

# 직접 테스트해서 확인한 부류코드만 사용한다 (검증 안 된 코드는 추가하지 않음)
CATEGORY_CODES = {
    "100": "식량작물",
    "200": "채소류",
    "500": "축산물",
    "600": "수산물",
}

# 채소류(200) 실제 품목 목록을 확인한 뒤 채워둔 동의어. 방향 규칙(재료명이 품목명에 포함)만으로는
# "애호박"이 "호박"에 매칭되지 않는 것처럼 놓치는 경우가 있어 자주 쓰는 것만 보정한다.
VEGETABLE_SYNONYMS = {
    "애호박": "호박",
    "단호박": "호박",
    "다진마늘": "마늘",
    "다진 마늘": "마늘",
    "다진생강": "생강",
}

# KAMIS 품목명이 한 글자짜리인 경우(소/닭/돼지) 부분일치가 오작동하지 않도록 별도 매핑
MEAT_SYNONYMS = {
    "소고기": "소", "쇠고기": "소",
    "돼지고기": "돼지",
    "닭고기": "닭",
}

# KAMIS 가격은 "20개", "1단" 처럼 개수 단위로 나오는 품목이 있어서, 레시피에 필요한 g(그램)량과
# 맞추려면 "개당 평균 몇 g인지" 가정이 필요하다. 완벽할 필요는 없고, 자주 나오는 품목만 채워둔다
# (지침 6번 원칙과 동일). 여기 없는 개수 단위 품목은 재료비 계산에서 제외되고 "환산 불가"로 표시된다.
AVG_PIECE_WEIGHT_G = {
    "호박": 300,       # 애호박 1개 평균 (단호박은 이보다 훨씬 무겁지만 매칭명이 같아 편의상 통일)
    "배추": 2000,      # 1포기
    "양배추": 1500,    # 1통
    "무": 1000,        # 1개
    "오이": 150,       # 1개
    "양파": 200,       # 1개
    "참외": 300,       # 1개
    "수박": 4500,      # 1통
    "멜론": 1500,      # 1개
    "토마토": 200,     # 1개
    "방울토마토": 15,  # 1개
    "파프리카": 150,   # 1개
    "피망": 80,        # 1개
    "상추": 15,        # 1장
    "깻잎": 2,         # 1장
}


def _kamis_unit_to_grams(unit: str, item_name: str) -> tuple[float | None, bool]:
    """
    KAMIS의 unit 문자열(예: "20kg", "1kg", "20개")이 실제로 몇 g에 해당하는 가격인지 계산한다.
    반환값: (그램 수 또는 None, is_estimated) - is_estimated는 AVG_PIECE_WEIGHT_G 추정치를
    썼는지 여부다 (kg/g처럼 정확히 환산되는 경우는 False).
    - 개/단/속/포기/통 같은 개수 단위는 AVG_PIECE_WEIGHT_G에 있는 품목만 추정 환산하고,
      없으면 (None, False)를 반환해서 "이 재료는 원가 계산에서 제외"하도록 한다.
    """
    if not unit:
        return None, False
    m = re.match(r"([\d.]+)\s*([가-힣a-zA-Z]*)", unit.strip())
    if not m:
        return None, False
    qty = float(m.group(1))
    suffix = m.group(2)

    if "kg" in suffix:
        return qty * 1000, False
    if suffix == "g":
        return qty, False

    # 개수 단위: 품목별 평균 중량표에 있을 때만 추정 환산
    avg_weight = AVG_PIECE_WEIGHT_G.get(item_name)
    if avg_weight is None:
        return None, False
    return qty * avg_weight, True


def estimate_recipe_total_cost(scaled_items: list[dict], all_items: list[dict]) -> dict:
    """
    레시피 재료들(이름 + 필요한 양(g) + 단위)을 KAMIS 가격과 매칭해서, 실제로 이 레시피를
    만드는 데 드는 재료비 총액(원)을 추정한다.
    - scaled_items: [{"name": ..., "amount": 숫자 또는 None, "unit": 문자열 또는 None}, ...]
      (portion_agent가 인분수에 맞춰 환산해둔 값. amount/unit이 없거나 단위가 "g"이 아니면 계산에서 제외)
    - 반환값의 total_cost는 "포함된 재료"만 합산한 부분 합계이며, 실제 총 재료비보다 적을 수 있다
      (지침 8번 원칙: 가격 정보는 참고용, 최신 정보는 공식 채널 재확인 권장).
    """
    included = []
    excluded = []

    for item in scaled_items:
        name = item.get("name")
        amount = item.get("amount")
        unit = item.get("unit")

        if is_staple(name):
            continue  # 조미료는 가격 등급과 마찬가지로 원가 계산에서도 제외
        if amount is None or unit != "g":
            excluded.append({"ingredient": name, "reason": "양(g) 정보가 없거나 g 단위가 아님"})
            continue

        matched = match_ingredient_price(name, all_items)
        if matched is None:
            excluded.append({"ingredient": name, "reason": "KAMIS 가격 매칭 안 됨"})
            continue

        lot_grams, is_estimated = _kamis_unit_to_grams(matched["unit"], matched["item_name"])
        if lot_grams is None or lot_grams <= 0:
            excluded.append({"ingredient": name, "reason": f"단위({matched['unit']}) 환산 불가"})
            continue

        price_per_g = matched["price"] / lot_grams
        cost = price_per_g * amount

        included.append({
            "ingredient": name,
            "matched_name": matched["item_name"],
            "amount_g": amount,
            "cost": cost,
            "is_estimated": is_estimated,
        })

    total_cost = sum(i["cost"] for i in included)
    return {"total_cost": total_cost, "included": included, "excluded": excluded}


def _extract_price(item: dict) -> float | None:
    """dpr1(당일)부터 dpr4(2주일전)까지 순서대로 값이 있는 걸 사용한다 (당일 데이터는 '-'인 경우가 많음)."""
    for key in ["dpr1", "dpr2", "dpr3", "dpr4"]:
        raw = item.get(key, "")
        if raw and raw != "-":
            try:
                return float(raw.replace(",", ""))
            except ValueError:
                continue
    return None


def fetch_category_prices(category_code: str) -> list[dict]:
    """부류코드 하나에 속한 품목들의 가격을 가져온다."""
    url = "http://www.kamis.or.kr/service/price/xml.do"
    params = {
        "action": "dailyPriceByCategoryList",
        "p_product_cls_code": "02",  # 도매
        "p_item_category_code": category_code,
        "p_country_code": "1101",    # 서울
        "p_regday": date.today().isoformat(),
        "p_convert_kg_yn": "Y",
        "p_cert_key": CERT_KEY,
        "p_cert_id": CERT_ID,
        "p_returntype": "json",
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"(경고) KAMIS 부류코드 {category_code} 조회 실패: {e}")
        return []

    if data.get("data", {}).get("error_code") != "000":
        return []

    items = data.get("data", {}).get("item", [])
    result = []
    for i in items:
        price = _extract_price(i)
        if price is None:
            continue
        result.append({
            "item_name": i.get("item_name"),
            "unit": i.get("unit"),
            "price": price,
            "category_code": category_code,
            "category_name": CATEGORY_CODES[category_code],
        })
    return result


def get_all_prices() -> list[dict]:
    """확인된 4개 부류 전체 가격을 가져온다."""
    all_items = []
    for code in CATEGORY_CODES:
        all_items.extend(fetch_category_prices(code))
    return all_items


def _category_medians(all_items: list[dict]) -> dict:
    """부류별 가격 중앙값 (같은 부류 안에서만 비교해야 단위 문제가 덜하다)."""
    by_cat = {}
    for i in all_items:
        by_cat.setdefault(i["category_code"], []).append(i["price"])
    return {code: statistics.median(prices) for code, prices in by_cat.items() if prices}


def match_ingredient_price(ingredient_name: str, all_items: list[dict]) -> dict | None:
    """
    재료명으로 KAMIS 품목을 찾는다.
    - 방향을 한 쪽으로만 허용한다: "재료명이 품목명 안에 포함되는" 경우만 매칭
      (예: "오징어"가 "마른오징어"에 포함 -> OK).
    - 반대 방향("품목명이 재료명 안에 포함")은 허용하지 않는다. 이걸 허용하면
      "콩"(대두)이라는 짧은 품목명이 "콩나물"(전혀 다른 재료) 안에 우연히 포함돼 있다는
      이유만으로 잘못 매칭되는 문제가 있었다 (실제 테스트에서 발견됨).
    - 정확히 이름이 같은 품목이 있으면 그것을 최우선으로 쓴다. 안 그러면 "배추"를 찾을 때
      "배추" 대신 "알배기배추"(다른 품종)에 걸릴 수 있다 (실제 채소류 목록 확인 중 발견).
    - 소/닭/돼지처럼 KAMIS 쪽 품목명이 축약형인 경우만 동의어 매핑으로 보정한다.
    """
    search_key = VEGETABLE_SYNONYMS.get(ingredient_name, MEAT_SYNONYMS.get(ingredient_name, ingredient_name))

    exact_matches = [i for i in all_items if i["item_name"] == search_key]
    matches = exact_matches if exact_matches else [i for i in all_items if search_key in i["item_name"]]
    if not matches:
        return None

    # 국내산과 수입산이 둘 다 있으면 "수입" 표시 없는 쪽(국내산)을 기본으로 우선한다.
    domestic = [m for m in matches if "수입" not in m["item_name"]]
    return domestic[0] if domestic else matches[0]


def estimate_recipe_price_tier(ingredient_names: list[str], all_items: list[dict]) -> dict:
    """
    레시피 재료들을 KAMIS 가격과 매칭해서, 같은 부류 내 중앙값 대비 상대적으로
    비싼 재료가 많은지 싼 재료가 많은지로 등급을 매긴다.
    (조미료는 이 함수를 부르기 전에 is_staple()로 걸러졌다고 가정)
    """
    medians = _category_medians(all_items)

    matched = []
    unmatched = []
    for name in ingredient_names:
        m = match_ingredient_price(name, all_items)
        if m is None:
            unmatched.append(name)
            continue
        median = medians.get(m["category_code"])
        ratio = (m["price"] / median) if median else None
        matched.append({**m, "ingredient": name, "ratio": ratio})

    # 매칭된 재료가 너무 적으면 등급을 매길 근거가 부족하다고 본다.
    # 원래는 2개만 매칭돼도 등급을 매겼는데, 매칭 2개 중 1개만 비싼 재료여도
    # "비싼 재료 비율 50%"가 되어 40% 기준을 넘겨버려서, 총 재료비가 몇십 원인 반찬이
    # "프리미엄"으로 표시되는 문제가 실사용에서 발견됐다(#68). 표본 2~3개로는 비율이
    # 재료 하나 차이로 크게 흔들려서 등급 자체가 신뢰하기 어려우므로, 최소 3개로 올렸다.
    total_names = len(ingredient_names) or 1
    if len(matched) < 3 or (len(matched) / total_names) < 0.3:
        return {"tier": "정보부족", "matched": matched, "unmatched": unmatched}

    ratios = [m["ratio"] for m in matched if m["ratio"] is not None]
    expensive = sum(1 for r in ratios if r >= 1.3)
    cheap = sum(1 for r in ratios if r <= 0.7)
    total = len(ratios) or 1

    if expensive / total >= 0.4:
        tier = "프리미엄"
    elif cheap / total >= 0.6:
        tier = "가성비"
    else:
        tier = "기본"

    return {"tier": tier, "matched": matched, "unmatched": unmatched}


if __name__ == "__main__":
    print("KAMIS 4개 부류 가격 조회 중...")
    all_items = get_all_prices()
    print(f"총 {len(all_items)}개 품목 가격 확인\n")

    test_ingredients = ["배추", "두부", "돼지고기", "새우", "콩나물", "계란", "애호박", "단호박", "마늘"]
    result = estimate_recipe_price_tier(test_ingredients, all_items)
    print(f"테스트 재료: {test_ingredients}")
    print(f"등급: {result['tier']}")
    for m in result["matched"]:
        ratio_txt = f"{m['ratio']:.2f}배" if m["ratio"] else "비교불가"
        print(f"  - {m['ingredient']} -> {m['item_name']}({m['unit']}): {m['price']:,.0f}원, 부류 중앙값 대비 {ratio_txt}")
    if result["unmatched"]:
        print(f"  매칭 안 된 재료: {result['unmatched']}")
