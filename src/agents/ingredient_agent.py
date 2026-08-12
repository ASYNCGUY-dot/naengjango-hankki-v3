"""
Ingredient Agent - 1단계
- 역할: 사용자가 입력한 재료 이름 리스트를 받아, 식품영양성분DB API에서 각 재료의 기본 영양정보를 찾아온다.
- 아직 Streamlit 연결 전이라, 재료 리스트는 코드 안에 하드코딩해서 테스트한다.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("NUTRITION_API_KEY")

# 기본 6대 영양소 (에너지~탄수화물)
NUTRIENT_FIELDS = {
    "AMT_NUM1": "energy_kcal",
    "AMT_NUM2": "water_g",
    "AMT_NUM3": "protein_g",
    "AMT_NUM4": "fat_g",
    "AMT_NUM5": "ash_g",
    "AMT_NUM6": "carbs_g",
}

# 상세 영양 가이드용 비타민·미네랄 (공식 코드표 "출력메세지_식품영양성분DB정보.xlsx" 확인 후 반영)
# 157개 필드 중 실제로 자주 안내되는 항목만 추림 (지침 6번 원칙: 완벽할 필요 없이 자주 쓰는 것만)
VITAMIN_MINERAL_FIELDS = {
    "AMT_NUM7": "sugar_g",          # 당류(g)
    "AMT_NUM8": "fiber_g",          # 식이섬유(g)
    "AMT_NUM9": "calcium_mg",       # 칼슘(mg)
    "AMT_NUM10": "iron_mg",         # 철(mg)
    "AMT_NUM12": "potassium_mg",    # 칼륨(mg)
    "AMT_NUM13": "sodium_mg",       # 나트륨(mg)
    "AMT_NUM14": "vitamin_a_ug",    # 비타민 A(μg RAE)
    "AMT_NUM18": "vitamin_b1_mg",   # 비타민 B1(mg)
    "AMT_NUM19": "vitamin_b2_mg",   # 비타민 B2(mg)
    "AMT_NUM20": "niacin_mg",       # 니아신(mg)
    "AMT_NUM21": "vitamin_c_mg",    # 비타민 C(mg)
    "AMT_NUM22": "vitamin_d_ug",    # 비타민 D(μg)
    "AMT_NUM111": "magnesium_mg",   # 마그네슘(mg)
    "AMT_NUM116": "zinc_mg",        # 아연(mg)
}


# 재료 자체(원재료) 정보를 우선하고, 없으면 가공식품, 그다음 음식(요리) 순으로 사용
GROUP_PRIORITY = ["원재료성", "가공식품", "음식"]

# DB에 등록된 표준명이 다른 자주 쓰는 재료 수동 매핑 (완벽할 필요 없음, 자주 쓰는 것만)
INGREDIENT_ALIASES = {
    "계란": "달걀_생것",
    "달걀": "달걀_생것",
}


def match_nutrition(ingredient_name: str) -> dict | None:
    """
    재료 이름 하나를 받아 식품영양성분DB에서 가장 적절한 결과를 찾아온다.
    - 이름이 정확히 일치하는 항목 중, 원재료성 > 가공식품 > 음식 순으로 우선 선택
    - 정확히 일치하는 게 하나도 없으면 첫 번째 검색 결과로 대체(근사치, is_exact_match=False로 표시)
    - 매칭되는 게 전혀 없으면 None을 반환한다.
    """
    # 매핑 테이블에 있으면 표준명으로 바꿔서 검색 (예: 계란 -> 달걀)
    search_name = INGREDIENT_ALIASES.get(ingredient_name, ingredient_name)

    url = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
    params = {
        "serviceKey": API_KEY,
        "pageNo": 1,
        "numOfRows": 500,   # 이 API가 허용하는 최대치. 정확한 이름의 재료를 찾기 위해 넉넉히 가져온다.
        "type": "json",
        "FOOD_NM_KR": search_name,
    }

    # 공공데이터포털 API는 가끔 응답이 늦을 때가 있어서, timeout을 20초로 넉넉히 주고
    # 그래도 안 되면 한 번 더 재시도한다 (최대 2번 시도 후 포기).
    response = None
    for attempt in range(2):
        try:
            response = requests.get(url, params=params, timeout=20)
            break
        except requests.exceptions.Timeout:
            if attempt == 0:
                print(f"  (경고) '{ingredient_name}' 요청이 20초 내에 응답하지 않아 재시도합니다...")
                continue
            print(f"  (경고) '{ingredient_name}' 재시도도 실패해서 건너뜁니다.")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  (경고) '{ingredient_name}' 요청 중 오류: {e}")
            return None

    data = response.json()
    items = data.get("body", {}).get("items", [])
    if not items:
        return None

    exact_matches = [i for i in items if i.get("FOOD_NM_KR") == search_name]

    is_exact = True
    if exact_matches:
        # 원재료성 > 가공식품 > 음식 우선순위로 정렬해서 첫 번째 선택
        exact_matches.sort(
            key=lambda i: GROUP_PRIORITY.index(i.get("DB_GRP_NM"))
            if i.get("DB_GRP_NM") in GROUP_PRIORITY else len(GROUP_PRIORITY)
        )
        item = exact_matches[0]
    else:
        # 정확히 일치하는 이름이 없으면 첫 검색 결과로 대체 (근사치임을 표시)
        item = items[0]
        is_exact = False

    result = {
        "input_name": ingredient_name,
        "matched_food_name": item.get("FOOD_NM_KR"),
        "food_code": item.get("FOOD_CD"),
        "db_group": item.get("DB_GRP_NM"),
        "is_exact_match": is_exact,
    }
    for raw_key, friendly_key in NUTRIENT_FIELDS.items():
        result[friendly_key] = item.get(raw_key)

    # 상세 영양 가이드용 비타민·미네랄도 함께 채워둔다 (값이 없으면 "" 그대로 들어옴)
    for raw_key, friendly_key in VITAMIN_MINERAL_FIELDS.items():
        result[friendly_key] = item.get(raw_key)

    return result


if __name__ == "__main__":
    # 테스트용 하드코딩 재료 리스트
    test_ingredients = ["두부", "계란", "콩나물"]

    for name in test_ingredients:
        result = match_nutrition(name)
        print(f"\n입력: {name}")
        if result is None:
            print("  -> 매칭되는 영양정보를 찾지 못했습니다.")
        else:
            match_note = "정확일치" if result["is_exact_match"] else "근사치(정확한 이름 없음)"
            print(f"  -> DB 매칭명: {result['matched_food_name']} ({result['db_group']}, {match_note})")
            print(f"     에너지: {result['energy_kcal']} kcal")
            print(f"     단백질: {result['protein_g']} g")
            print(f"     지방: {result['fat_g']} g")
            print(f"     탄수화물: {result['carbs_g']} g")
            print(f"     [상세] 칼슘: {result['calcium_mg']} mg / 철: {result['iron_mg']} mg / "
                  f"비타민C: {result['vitamin_c_mg']} mg / 나트륨: {result['sodium_mg']} mg")
