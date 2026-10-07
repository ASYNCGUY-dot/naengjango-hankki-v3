"""
Price Agent [선택] - 가격대별 메뉴 등급 + 재료비 총액 추정
- KAMIS(농산물유통정보) API로 식량작물·채소류·특용작물·과일류·축산물·수산물 6개 부류의
  **서울 소매가격**을 가져와서, 레시피 재료가 각 부류 안에서 상대적으로 비싼 편인지 싼 편인지를 비교한다
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
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from dotenv import load_dotenv

from portion_agent import LEADING_LABEL
from recommendation_agent import STAPLE_SEASONINGS

load_dotenv()
CERT_KEY = os.getenv("KAMIS_CERT_KEY")
CERT_ID = os.getenv("KAMIS_CERT_ID")

# 직접 테스트해서 확인한 부류코드만 사용한다 (검증 안 된 코드는 추가하지 않음).
# 특용작물(300)·과일류(400)는 2026-09-29에 도매·소매 모두 조회되는 것을 확인하고 넣었다.
# 버섯·호두·땅콩과 사과·레몬·배가 여기 있다 - 빠져 있던 동안 레시피 재료 중 이것들은
# 전부 "가격 정보 없음"이었다.
CATEGORY_CODES = {
    "100": "식량작물",
    "200": "채소류",
    "300": "특용작물",
    "400": "과일류",
    "500": "축산물",
    "600": "수산물",
}

# 소매(01)가격을 쓴다 (2026-09-29, 원래는 도매 02).
#
# 이 값으로 계산하는 건 "이 한 끼 재료비"라 사람이 장보며 내는 값이어야 한다. 도매는 단위가
# 10kg·20kg·40kg이라 한 끼 분량으로 나누면 오차가 크고, 가격 자체도 소비자가 내는 값이 아니다.
# 소매는 1kg·100g·1개·1마리처럼 장보기 단위로 온다. 운영 레시피 재료로 재보니 매칭률도
# 소매가 조금 높았다(6부류 기준 28.9% 대 27.0%) - 우유처럼 소매에만 있는 품목이 있다.
PRODUCT_CLS_CODE = "01"

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
    # 닭 부위. KAMIS 소매 닭은 "육계"·"절단육"뿐이라 부위 가격은 없다 - 닭 전체 가격으로 본다.
    "닭가슴살": "닭", "닭다리살": "닭", "닭다릿살": "닭", "닭봉": "닭", "닭날개": "닭", "닭안심살": "닭",
}

# 레시피와 KAMIS가 같은 것을 다른 이름으로 부르는 경우 (2026-09-29).
#
# 지어내지 않았다. 가격이 안 붙는 재료 상위 목록과 KAMIS 소매 품목·품종 목록을 나란히 놓고,
# 같은 것이 확실한 것만 골랐다. 레시피 쪽 등장 횟수는 운영 데이터 기준이다.
NAME_SYNONYMS = {
    "달걀": "계란",       # 163회. KAMIS는 "계란"(특란10구·30구)으로만 올린다
    "홍고추": "붉은고추",  # 114회
    "청고추": "풋고추",    # 53회
    "청피망": "피망",      # 30회
    "새우살": "새우",
}

# 가격 계산에서 뺄 조미료 (2026-09-29).
#
# 원래는 recommendation_agent.is_staple()을 그대로 썼는데, 그 판정은 **부분 문자열**이라
# "파"가 들어간 양파·파프리카·파인애플·파슬리와 "마늘"이 들어간 모든 것이 조미료로 빠졌다.
# 그래서 재료비에 양파가 한 번도 들어간 적이 없었다. 추천 쪽 판정은 영향 범위가 커서
# 그대로 두고, 가격에서만 **이름이 정확히 조미료인 것**을 뺀다.
#
# 목록에 더한 것은 가격이 안 붙는 재료 상위권에 있던 기름·술·당류다. 한 끼마다 사는 것이
# 아니라 집에 두고 쓰는 것이고, KAMIS 범위 밖이라 등급의 매칭 비율만 떨어뜨렸다.
PRICE_EXTRA_STAPLES = {
    "후춧가루", "통후추", "올리브오일", "올리브유", "올리고당", "맛술", "청주", "정종", "튀김기름",
}
_STAPLE_PREFIXES = ("다진", "간")


def _base_and_hint(name: str) -> tuple[str, str]:
    """"돼지고기(삼겹살)"처럼 괄호가 붙은 재료명을 (돼지고기, 삼겹살)로 나눈다.

    레시피 재료명에는 파싱 때 닫는 괄호가 잘린 "소고기(등심" 같은 것도 섞여 있다. 괄호 앞을
    품목으로, 괄호 안을 품종 힌트로 쓴다. 원래는 괄호째 비교해서 이런 재료가 전부 안 붙었다.

    "(속재료) 단호박"처럼 **앞에** 붙은 괄호는 분류 표시라 떼고 본다(2026-10-01). 떼지 않으면
    괄호 앞이 빈 문자열이 되고, 빈 문자열은 모든 품목 이름에 들어 있어서 아무 품목에나 붙었다.
    "재료 닭가슴살"·"[주재료]닭다리살"처럼 원본 텍스트를 나눌 때 남은 분류어도 같이 뗀다.
    """
    name = LEADING_LABEL.sub("", name or "").strip()
    if "(" not in name:
        return name, ""
    base, _, rest = name.partition("(")
    return base.strip(), rest.split(")")[0].strip()


def is_price_staple(name: str) -> bool:
    """가격 계산에서 뺄 조미료인가. 이름이 정확히 조미료일 때만 True다."""
    base = _base_and_hint(name)[0].replace(" ", "")
    staples = STAPLE_SEASONINGS | PRICE_EXTRA_STAPLES
    if base in staples:
        return True
    return any(base.startswith(p) and base[len(p):] in staples for p in _STAPLE_PREFIXES)

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
    # 소매로 바꾸며 새로 생긴 단위. 추정치라 화면에 "추정"으로 표시된다.
    "계란": 60,        # 1구 (특란 기준)
    "우유": 1000,      # 1L를 1000g으로 본다
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

        if is_price_staple(name):
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
            "price_day": matched.get("price_day"),
        })

    total_cost = sum(i["cost"] for i in included)
    return {"total_cost": total_cost, "included": included, "excluded": excluded}


def _extract_price(item: dict) -> float | None:
    """dpr1(당일)부터 dpr4(2주일전)까지 순서대로 값이 있는 걸 사용한다 (당일 데이터는 '-'인 경우가 많음)."""
    return _extract_price_and_day(item)[0]


def _extract_price_and_day(item: dict) -> tuple[float | None, str | None]:
    """가격과, 그 가격이 어느 날 값인지("당일 (09/30)")를 함께 준다.

    칸의 뜻은 KAMIS 응답의 day1~day7 라벨로 확인했다(2026-09-29): dpr1 당일, dpr2 1일전,
    dpr3 1주일전, dpr4 2주일전, dpr5 1개월전, dpr6 1년전, dpr7 평년. 2주일 전(dpr4)까지만
    쓴다 - 그보다 오래된 값을 오늘 재료비로 보여주면 안 된다. 화면은 이 라벨로 "몇 월 며칠
    시세인지"를 밝힌다.
    """
    for n in (1, 2, 3, 4):
        raw = item.get(f"dpr{n}", "")
        if raw and raw != "-":
            try:
                price = float(raw.replace(",", ""))
            except ValueError:
                continue
            # 0원은 값이 없는 것이다. 닭 절단육이 당일 "0"으로 와서 닭 재료비가 0원으로 나왔다.
            if price > 0:
                return price, item.get(f"day{n}")
    return None, None


def _price_unit(raw_unit: str) -> str:
    """p_convert_kg_yn=Y로 받은 가격이 실제로 어느 단위의 값인지 돌려준다.

    Y는 무게 단위 품목의 **가격만** 1kg당으로 바꾸고 unit은 원래 값("100g")으로 둔다. 같은 날
    Y와 N을 나란히 받아 가격 있는 소매 품목 177개 전부가 "무게 단위면 1kg당, 개수 단위면
    그대로"인 것을 확인했다(2026-10-01). unit을 그대로 믿으면 100g 품목은 10배, 깻잎(50g)은
    20배 비싸게, 쌀(20kg)은 20배 싸게 계산된다.
    """
    if re.fullmatch(r"[\d.]+\s*(kg|g)", (raw_unit or "").strip()):
        return "1kg"
    return raw_unit


# 자료가 없는 날이면 며칠 전까지 거슬러 올라가 볼지. 추석 같은 긴 연휴를 덮는 값이다.
MAX_LOOKBACK_DAYS = 7


def fetch_category_prices(category_code: str) -> list[dict]:
    """부류코드 하나에 속한 품목들의 가격을 가져온다.

    조회 날짜에 자료가 없으면 하루씩 거슬러 올라간다(2026-10-04). 일요일을 넣으면 KAMIS는
    {"data": ["001"]}을 돌려준다 - 같은 날 토요일·평일 날짜는 정상이었다. 이 모양을 처리하지
    못해 AttributeError가 났고, 라우터가 503으로 바꿔서 일요일마다 재료비 카드가 안 나왔다.
    어느 날 시세인지는 응답의 날짜 라벨이 그대로 말해 준다.
    """
    url = "http://www.kamis.or.kr/service/price/xml.do"
    payload = None
    for days_back in range(MAX_LOOKBACK_DAYS):
        params = {
            "action": "dailyPriceByCategoryList",
            "p_product_cls_code": PRODUCT_CLS_CODE,
            "p_item_category_code": category_code,
            "p_country_code": "1101",    # 서울
            "p_regday": (date.today() - timedelta(days=days_back)).isoformat(),
            # Y: 무게 단위 가격을 1kg당으로 받는다. 부류 안 가격 비교(등급)가 같은 단위로 되게 하려는
            # 것이다. 단 unit은 안 바뀌어 온다 - 저장할 때 _price_unit()으로 맞춘다.
            "p_convert_kg_yn": "Y",
            "p_cert_key": CERT_KEY,
            "p_cert_id": CERT_ID,
            "p_returntype": "json",
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            # 응답 자체가 없으면 날짜 탓이 아니다. 거슬러 올라가도 같은 실패만 반복된다.
            print(f"(경고) KAMIS 부류코드 {category_code} 조회 실패: {e}")
            return []

        payload = data.get("data") if isinstance(data, dict) else None
        if isinstance(payload, dict):
            break
        # payload가 dict가 아니면(["001"]) 그 날짜에 자료가 없는 것이다. 하루 전을 본다.
    else:
        return []

    if payload.get("error_code") != "000":
        return []

    items = payload.get("item", [])
    result = []
    for i in items:
        price, price_day = _extract_price_and_day(i)
        if price is None:
            continue
        result.append({
            "item_name": i.get("item_name"),
            # 품종. "파" 아래에 대파·쪽파가, "돼지" 아래에 삼겹살·목심이 있다. 이게 없으면
            # 대파를 찾아도 쪽파 가격이 나올 수 있다(match_ingredient_price 참고).
            "kind_name": i.get("kind_name"),
            # 가격과 같은 단위로 맞춘다(_price_unit 참고). 응답의 unit을 그대로 쓰면 안 된다.
            "unit": _price_unit(i.get("unit")),
            "price": price,
            "price_day": price_day,
            "category_code": category_code,
            "category_name": CATEGORY_CODES[category_code],
        })
    return result


def get_all_prices() -> list[dict]:
    """확인된 부류 전체 가격을 가져온다.

    6부류를 동시에 부른다(2026-10-01). 하나씩 부르면 로컬에서 5초, 배포 서버(해외)에서
    재료비 카드가 11.6초 걸렸다. 동시 6건으로 5회 연속 조회해 빠지는 부류가 없는 것을
    확인했다(로컬 1.6~1.8초). 결과는 응답 도착 순이 아니라 부류 순서로 합친다 - 품목
    순서가 매칭의 동점 처리에 쓰인다.
    """
    with ThreadPoolExecutor(max_workers=len(CATEGORY_CODES)) as pool:
        per_category = list(pool.map(fetch_category_prices, CATEGORY_CODES))
    all_items = [item for items in per_category for item in items]

    # 부류 하나가 비면 조용히 넘기지 않는다(2026-10-07). 넘기면 호출부의 캐시가 "일부만 있는
    # 결과"를 정상으로 알고 10분간 붙잡아서, 그동안 그 부류 재료가 전부 "가격 정보 없음"이 됐다.
    # 받은 것은 버리지 않고 예외에 실어 보낸다 - 어떻게 쓸지는 호출부가 정한다.
    missing = [code for code, items in zip(CATEGORY_CODES, per_category) if not items]
    if missing:
        raise PartialPricesError(all_items, missing)
    return all_items


class PartialPricesError(Exception):
    """KAMIS 부류 일부만 받았다. 받은 품목은 items에, 못 받은 부류코드는 missing에 있다."""

    def __init__(self, items: list[dict], missing: list[str]):
        super().__init__(f"KAMIS 부류 {', '.join(missing)} 조회 실패")
        self.items = items
        self.missing = missing


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
    base, hint = _base_and_hint(ingredient_name)
    if not base:
        return None  # 빈 이름은 모든 품목 이름의 부분 문자열이라 아무 데나 붙는다

    # 1) 품종 이름으로 먼저 찾는다 (2026-09-29). "청양고추"는 품목 "풋고추"의 품종이고
    #    "삼겹살"은 품목 "돼지"의 품종이다. 품목 이름만 보면 청양고추는 아예 못 찾고,
    #    대파는 같은 "파" 아래의 쪽파 가격을 집을 수 있다.
    #    여러 품목에 같은 품종이 있으면(갈비는 돼지에도 소에도 있다) 어느 쪽인지 알 수 없으니
    #    품종 매칭을 포기하고 아래 규칙으로 넘어간다.
    #    다만 국산·수입은 모호함으로 치지 않는다. "돼지"와 "수입 돼지고기"가 둘 다 삼겹살을
    #    갖는데, 이걸 모호하다고 보면 실제 데이터에서 삼겹살이 통째로 안 붙는다. 국산을 우선한다.
    kind_hits = [i for i in all_items if _kind_base(i.get("kind_name")) == base]
    if kind_hits:
        pool = [i for i in kind_hits if "수입" not in i["item_name"]] or kind_hits
        if len({i["item_name"] for i in pool}) == 1:
            return _prefer_domestic(pool)

    search_key = NAME_SYNONYMS.get(base) or VEGETABLE_SYNONYMS.get(base) or MEAT_SYNONYMS.get(base) or base

    # 2) "돼지고기(삼겹살)"처럼 괄호 안에 품종이 적혀 있으면, 그 품목 안에서 품종을 찾는다.
    if hint:
        hinted = [
            i for i in all_items
            if i["item_name"] == search_key and _kind_base(i.get("kind_name")) == hint
        ]
        if hinted:
            return _prefer_domestic(hinted)

    exact_matches = [i for i in all_items if i["item_name"] == search_key]
    matches = exact_matches if exact_matches else [i for i in all_items if search_key in i["item_name"]]
    if not matches:
        return None

    return _prefer_domestic(matches)


def _kind_base(kind_name: str | None) -> str:
    """KAMIS 품종명에서 괄호 속 단위를 뗀다: "풋고추(녹광 등)(1kg)" -> "풋고추"."""
    return re.sub(r"\([^()]*\)", "", kind_name or "").strip()


def _prefer_domestic(matches: list[dict]) -> dict:
    """후보 여럿 중 대표 하나를 고른다: 국산 중, 같은 단위 안에서, 가격이 가운데인 것.

    국내산과 수입산이 둘 다 있으면 "수입" 표시 없는 쪽(국내산)을 우선한다. 땅콩·고등어는 품목이
    아니라 품종 이름에 "수입"을 적으므로 둘 다 본다.

    예전에는 국산 중 **첫 번째**를 썼다(2026-10-01까지). 응답 순서는 기준이 아니다 - 소는 첫
    번째가 안심 1등급이라 "쇠고기"만 적힌 운영 레시피 55행이 소 품종 중앙값의 2.46배로
    계산됐다. 부위·등급을 모르면 가운데 값을 쓴다(짝수면 낮은 쪽, 매번 같은 답이 나오게).
    단위가 다르면 값을 바로 비교할 수 없으니(계란 10구와 30구) 첫 후보의 단위 안에서만 고른다.
    """
    domestic = [
        m for m in matches
        if "수입" not in m["item_name"] and "수입" not in (m.get("kind_name") or "")
    ]
    pool = domestic or matches
    same_unit = [m for m in pool if m.get("unit") == pool[0].get("unit")]
    by_price = sorted(same_unit, key=lambda m: m["price"])
    return by_price[(len(by_price) - 1) // 2]


def estimate_recipe_price_tier(ingredient_names: list[str], all_items: list[dict]) -> dict:
    """
    레시피 재료들을 KAMIS 가격과 매칭해서, 같은 부류 내 중앙값 대비 상대적으로
    비싼 재료가 많은지 싼 재료가 많은지로 등급을 매긴다.

    조미료는 여기서 거른다. 원래는 "부르기 전에 걸러졌다고 가정"했는데 라우터가 거르지 않고
    재료 전체를 넘기고 있어서, 소금·간장 같은 것이 "매칭 안 됨"으로 쌓여 매칭 비율을 깎고
    멀쩡한 레시피를 "정보부족"으로 만들었다.
    """
    ingredient_names = [n for n in ingredient_names if not is_price_staple(n)]
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
    print("KAMIS 부류별 소매 가격 조회 중...")
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
