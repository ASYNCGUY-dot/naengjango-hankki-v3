"""
Tagging Agent
- 역할: 레시피DB(COOKRCP01) 데이터를 recipes 테이블에 저장하고,
        재료 텍스트·영양정보를 바탕으로 recipe_tags 테이블에 자동 태깅한다.
        조리 단계(steps_json)도 함께 저장한다.
- 태그 종류(tag_type): category(카테고리), allergy(알레르기 유발물질),
                       nutrition_group(영양군), ingredient(재료명)
- 참고: 알레르기 판단과 재료명 추출은 완벽한 파싱이 아니라 규칙 기반 근사치다.
        지침대로 최종 확인은 사용자 책임이며, 이 태깅은 참고용 필터링이다.
"""

import re
import sqlite3
import json

DB_PATH = "data/app.db"

# 식품표시광고법 시행규칙 별표2 기준 (검색 확인, 22개 표시대상 중 확인된 19개 명칭)
ALLERGENS = [
    "난류", "알류", "계란", "달걀",   # 알류(가금류)
    "우유", "메밀", "땅콩", "대두", "밀",
    "고등어", "게", "새우", "돼지고기",
    "복숭아", "토마토", "아황산", "호두",
    "닭고기", "쇠고기", "소고기", "오징어",
    "굴", "전복", "홍합", "잣",
]

# 재료 텍스트에서 흔히 붙는 손질 방식 표현 (제거 대상, 완벽할 필요 없음)
PREP_PREFIXES = ["다진 ", "채썬 ", "슬라이스 ", "잘게 썬 ", "다지고 ", "으깬 "]
TRAILING_WORDS = ["약간", "적당량", "조금", "소량"]
SKIP_WORDS = {"고명", "양념장", "양념", "소스", "밑간"}

# 섹션 구분용 라벨 단어 (재료 텍스트가 "[재료] 이름1, [양념] 이름2, ..." 처럼 여러 구간으로
# 나뉘어 있을 때, 맨 앞의 "[...]" 하나만 지워지고 나머지는 "재료 ", "육수 " 처럼 대괄호 없이
# 한 토큰에 그대로 붙어 남는 경우가 있어서(#68에서 실측 확인) 별도로 제거한다.
SECTION_LABEL_PREFIXES = [
    "[재료]", "[양념]", "[육수]", "[주재료]", "[소스]",
    "재료 ", "육수 ", "양념 ", "소스 ",
]


def clean_ingredient_name(name: str) -> str:
    """
    재료명 추출 과정에서 흔히 남는 찌꺼기를 정리한다 (#68).
    - 섹션 라벨("재료 ", "[주재료]" 등)이 실제 재료명 앞에 그대로 붙어 남은 경우 제거
    - "이름(50g)"에서 숫자 기준으로 자르다 보니 "이름(" 또는 "이름(등심"처럼 여는 괄호가
      안 닫힌 채 남는 경우 -> 괄호와 그 뒤 내용을 통째로 제거 (실제 재료명은 괄호 앞부분)
    - 괄호가 짝이 맞게 닫혀 있는 경우("고등어(1마리=250g)"처럼 수량이 통째로 이름 컬럼에
      들어있는 경우, recipe_ingredients 테이블에서 확인됨, #73)도 그 괄호 구간을 통째로
      제거한다 - 안 그러면 숫자가 섞인 채로 남아서 "숫자가 있으면 재료명이 아니다"로 보는
      필터(_is_valid_ingredient_name)에 걸려 재료 자체가 통째로 누락돼버린다.
    - 짝이 안 맞는 고아 괄호 문자가 남으면 마지막으로 한 번 더 벗겨낸다
    완벽한 파싱이 목표가 아니라, 화면에 지저분한 문자열이 노출되지 않게 하는 게 목적이다.
    """
    cleaned = name.strip()
    for label in SECTION_LABEL_PREFIXES:
        if cleaned.startswith(label):
            cleaned = cleaned[len(label):].strip()

    if "(" in cleaned and cleaned.count("(") > cleaned.count(")"):
        cleaned = cleaned.split("(")[0].strip()
    elif "(" in cleaned and ")" in cleaned:
        # 괄호 짝은 맞는데 안에 수량이 들어있는 경우("고등어(1마리=250g)") - 괄호 구간을
        # 통째로 지운다. re.sub이 아니라 간단히 반복 치환해도 되지만, 이 데이터 특성상
        # 괄호가 중첩되는 경우는 없어서 정규식 하나로 충분하다.
        cleaned = re.sub(r"\([^()]*\)", "", cleaned).strip()

    cleaned = cleaned.strip("()").strip()
    return cleaned


def tag_allergy(ingredient_text: str) -> list[str]:
    """재료 텍스트(RCP_PARTS_DTLS)에서 알레르기 유발물질 키워드를 찾아 리스트로 반환"""
    found = []
    for allergen in ALLERGENS:
        if allergen in ingredient_text:
            found.append(allergen)
    return found


def tag_nutrition_group(energy, carbs, protein, fat) -> str:
    """
    탄수화물/단백질/지방이 칼로리에서 차지하는 비중을 계산해서
    가장 비중이 큰 영양소 기준으로 태그를 매긴다.
    (탄수화물 1g=4kcal, 단백질 1g=4kcal, 지방 1g=9kcal 기준)
    """
    try:
        carb_kcal = float(carbs or 0) * 4
        protein_kcal = float(protein or 0) * 4
        fat_kcal = float(fat or 0) * 9
    except ValueError:
        return "미분류"

    total = carb_kcal + protein_kcal + fat_kcal
    if total == 0:
        return "미분류"

    ratios = {
        "고탄수화물": carb_kcal / total,
        "고단백": protein_kcal / total,
        "고지방": fat_kcal / total,
    }
    top_tag = max(ratios, key=ratios.get)
    if ratios[top_tag] < 0.5:
        return "균형"
    return top_tag


def extract_ingredient_names(parts_dtls: str, menu_name: str = "") -> list[str]:
    """
    RCP_PARTS_DTLS 텍스트에서 재료 이름만 대략 뽑아낸다. (완벽한 파싱이 목표가 아님)
    처리하는 것: 대괄호([1인분] 등) 제거, 콤마/줄바꿈 분리, 수량 이후 텍스트 제거,
                손질 방식 접두어 제거, 뒤에 붙는 "약간"류 단어 제거, 섹션 제목/레시피명 중복 제외
    """
    text = re.sub(r"^\[.*?\]", "", parts_dtls)  # "[1인분]" 같은 머리말 제거
    tokens = re.split(r"[,\n]", text)

    names = []
    for token in tokens:
        token = token.strip().lstrip("·●・-")
        if not token:
            continue

        # "양념장 : 저염간장" 처럼 콜론이 있으면 콜론 뒤만 사용
        if ":" in token:
            token = token.split(":", 1)[1].strip()
        if not token or token in SKIP_WORDS:
            continue

        # 숫자가 나오는 지점부터 잘라서 수량 정보 제거 ("연두부 75g(3/4모)" -> "연두부")
        name = re.split(r"\d", token)[0].strip()

        for prefix in PREP_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()

        for trailing in TRAILING_WORDS:
            if name.endswith(trailing):
                name = name[: -len(trailing)].strip()

        # 숫자 기준으로 자르다 보니 "돼지고기(", "돼지고기(등심"처럼 여는 괄호가 안 닫힌 채
        # 남거나, 섹션 라벨("재료 ", "[주재료]" 등)이 그대로 붙어 남는 경우가 있어 정리한다 (#68).
        name = clean_ingredient_name(name)

        if not name or name in SKIP_WORDS:
            continue
        # 레시피 제목이 재료 텍스트 첫머리에 그대로 반복되는 경우 제외
        if menu_name and name.replace(" ", "") == menu_name.replace(" ", ""):
            continue

        names.append(name)

    return names


def extract_steps(recipe: dict) -> list[dict]:
    """MANUAL01~20(설명)과 MANUAL_IMG01~20(이미지)을 짝지어 순서대로 리스트로 만든다."""
    steps = []
    for i in range(1, 21):
        num = f"{i:02d}"
        text = (recipe.get(f"MANUAL{num}") or "").strip()
        image = (recipe.get(f"MANUAL_IMG{num}") or "").strip()
        if not text:
            continue
        steps.append({"step": i, "text": text, "image": image or None})
    return steps


def insert_recipe_with_tags(
    cur, recipe: dict, source_api: str = "COOKRCP01",
    submitted_by: int | None = None, status: str = "approved",
) -> int:
    """
    레시피 하나를 recipes 테이블에 넣고, 태깅 결과를 recipe_tags 테이블에 넣는다.
    source_api/submitted_by/status를 넘기면 유저가 등록한 레시피도 같은 함수로 저장할 수 있다
    (user_recipe_agent.py에서 재사용, #32/#35). status="pending"이면 관리자 승인 전까지
    다른 사용자에게 보이지 않는다 (중복된 메뉴명으로 등록된 경우).
    """

    menu_name = recipe.get("RCP_NM")

    nutrients = {
        "energy_kcal": recipe.get("INFO_ENG"),
        "carbs_g": recipe.get("INFO_CAR"),
        "protein_g": recipe.get("INFO_PRO"),
        "fat_g": recipe.get("INFO_FAT"),
        "sodium_mg": recipe.get("INFO_NA"),
    }
    steps = extract_steps(recipe)

    cur.execute("""
        INSERT INTO recipes (menu_name, cook_method, category, calorie, nutrients_json, image_url, youtube_url, source_api, steps_json, submitted_by, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        menu_name,
        recipe.get("RCP_WAY2"),
        recipe.get("RCP_PAT2"),
        recipe.get("INFO_ENG"),
        json.dumps(nutrients, ensure_ascii=False),
        recipe.get("ATT_FILE_NO_MAIN") or recipe.get("MANUAL_IMG01"),
        None,
        source_api,
        json.dumps(steps, ensure_ascii=False),
        submitted_by,
        status,
    ))
    recipe_id = cur.lastrowid

    # 1) 카테고리 태그
    if recipe.get("RCP_PAT2"):
        cur.execute(
            "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
            (recipe_id, "category", recipe["RCP_PAT2"])
        )

    # 2) 알레르기 태그 (재료 텍스트 기반)
    for allergen in tag_allergy(recipe.get("RCP_PARTS_DTLS", "")):
        cur.execute(
            "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
            (recipe_id, "allergy", allergen)
        )

    # 3) 영양군 태그
    nutrition_tag = tag_nutrition_group(
        recipe.get("INFO_ENG"), recipe.get("INFO_CAR"),
        recipe.get("INFO_PRO"), recipe.get("INFO_FAT")
    )
    cur.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
        (recipe_id, "nutrition_group", nutrition_tag)
    )

    # 4) 재료 태그
    for name in extract_ingredient_names(recipe.get("RCP_PARTS_DTLS", ""), menu_name):
        cur.execute(
            "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
            (recipe_id, "ingredient", name)
        )

    return recipe_id


if __name__ == "__main__":
    import os

    # 전체 데이터(cookrcp01_all.json) > 50개 샘플 > 초기 5개 샘플 순으로 우선 사용
    source_path = "data/api_samples/cookrcp01_all.json"
    if not os.path.exists(source_path):
        source_path = "data/api_samples/cookrcp01_50.json"
    if not os.path.exists(source_path):
        source_path = "data/api_samples/cookrcp01_sample.json"
        print(f"(참고) {source_path} 파일이 없어서 초기 샘플(5개)을 대신 사용합니다.")

    with open(source_path, "r", encoding="utf-8") as f:
        sample = json.load(f)

    recipes = sample["COOKRCP01"]["row"]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 다시 실행해도 중복 저장되지 않도록, 레시피 관련 테이블을 먼저 비운다.
    # (레시피 id가 바뀌므로 거기에 딸린 recipe_ingredients/reviews/review_summaries도 함께 비움)
    print("주의: 실행 전 Streamlit을 완전히 종료했는지 확인하세요 (동시 접근 시 DB 손상 위험).")
    cur.execute("DELETE FROM recipe_tags")
    cur.execute("DELETE FROM recipe_ingredients")
    cur.execute("DELETE FROM review_summaries")
    cur.execute("DELETE FROM reviews")
    cur.execute("DELETE FROM recipes")

    for recipe in recipes:
        recipe_id = insert_recipe_with_tags(cur, recipe)

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM recipes")
    print(f"총 {cur.fetchone()[0]}개 레시피 저장 완료 (source: {source_path})")
    print("다음으로 portion_agent.py -> youtube_agent.py 순서로 재실행하세요.")

    conn.close()
