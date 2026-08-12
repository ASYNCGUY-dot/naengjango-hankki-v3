"""
Recommendation Agent - 후보 추리기
- 역할: 사용자 프로필(알레르기)과 보유 재료를 바탕으로 recipes/recipe_tags 테이블에서 추천 후보를 추리고 정렬한다.
- 재료 매칭은 Tagging Agent가 만들어둔 recipe_tags(tag_type='ingredient')와 비교하는 방식이다.
"""

import json
import re
import sqlite3

from tagging_agent import clean_ingredient_name

DB_PATH = "data/app.db"

# 자주 쓰는 재료 동의어 매핑 (완벽할 필요 없음, 자주 쓰는 것만 - 지침 8번 원칙)
SYNONYM_MAP = {
    "계란": "달걀",
    "쇠고기": "소고기",
}

# 2026-07 8차 개정(#74): SYNONYM_MAP은 "이름 하나 -> 이름 하나"만 바꿔주는 1:1 매핑이라,
# "삼겹살"처럼 부위 이름이 완전히 다른 단어인 경우는 처리 못 한다("삼겹살"과 "돼지고기"는
# 부분 문자열 관계가 아니라서 ingredients_match()의 부분일치 규칙으로도 안 걸림). 그래서
# "이 부위들은 서로 대체 가능한 같은 고기(생선)로 본다"는 그룹을 따로 둔다. 자주 쓰는 3가지
# (돼지고기/소고기/참치)만 우선 다뤘고(지침 8번 원칙 - 완벽한 목록일 필요 없음), 실제
# recipe_tags/recipe_ingredients에 있는 표기(예: "돼지고기목살", "쇠고기(우둔")도 반영했다.
# "안심"/"등심"/"갈비"/"사태"처럼 돼지·소 양쪽에 다 있는 애매한 부위명은, 사용자가 요청한
# "대체 재료로 쓸 수 있으면 된다"는 기준에 따라 양쪽 그룹에 다 넣었다 - 정확히 어느 동물인지
# 몰라도 "이 요리에 넣을 수 있는 비슷한 고기"로 보는 게 실용적이기 때문이다.
PORK_GROUP = {
    "돼지고기", "돼지", "돈육", "삼겹살", "오겹살", "우삼겹", "대패삼겹살",
    "목살", "목심", "전지", "후지", "앞다리살", "뒷다리살", "가브리살", "갈매기살",
    "항정살", "돈등심", "돈안심", "제육", "돼지갈비", "등갈비", "족발",
    # 소고기와 겹치는 애매한 부위(대체재 논거로 양쪽에 포함)
    "안심", "등심", "갈비", "사태",
}
BEEF_GROUP = {
    "소고기", "쇠고기", "우육", "한우", "채끝살", "채끝", "부채살",
    "살치살", "차돌박이", "차돌", "양지", "양지살", "우둔살", "우둔", "설도",
    "설깃살", "보섭살", "꽃등심", "치마살", "안창살", "토시살", "제비추리",
    "업진살", "소갈비", "L.A갈비",
    # 돼지고기와 겹치는 애매한 부위(대체재 논거로 양쪽에 포함)
    "안심", "등심", "갈비", "사태",
}
TUNA_GROUP = {
    "참치", "참치살", "다랑어", "참다랑어", "황다랑어", "눈다랑어",
    "중뱃살", "대뱃살", "붉은살",
}
INGREDIENT_GROUPS: list[set[str]] = [PORK_GROUP, BEEF_GROUP, TUNA_GROUP]


def _belongs_to_group(name: str, group: set[str]) -> bool:
    """이 재료명 안에 그룹의 부위 키워드가 하나라도 포함돼 있는지 (부분일치 - "돼지고기(삼겹살"
    처럼 태그가 지저분해도 "삼겹살"이 들어있으면 인정하기 위함)."""
    return any(member in name for member in group)


def _same_ingredient_group(a: str, b: str) -> bool:
    """a와 b가 같은 부위 그룹(돼지고기/소고기/참치)에 속하는지 - 서로 대체 가능한 재료로 본다."""
    return any(_belongs_to_group(a, group) and _belongs_to_group(b, group) for group in INGREDIENT_GROUPS)


# 2026-07 9차 개정(#76): 겹침 "개수"만 보면, 두부·양배추·깻잎처럼 흔한 채소/두부 4개가 겹치는
# 요리가, 참치·고등어처럼 진짜 보유한 단백질(육류·생선) 재료를 1개 쓰는 요리보다 항상 이겨버린다.
# 실사용 확인: 고등어·갈치·참치·전지(돼지고기)를 보유했는데, 상위 3개 후보가 전부 두부/채소만
# 매칭되고 단백질은 하나도 안 썼다. 그래서 "보유한 단백질 재료를 실제로 쓰는 레시피"를 그렇지
# 않은 레시피보다 category_tier 다음으로 우선하는 기준을 추가한다 - 겹침 개수가 적어도, 단백질을
# 실제로 쓰는 요리가 채소만 잔뜩 겹치는 요리보다 "이 재료로 만든 요리"라는 실감이 훨씬 크기
# 때문이다. PORK_GROUP/BEEF_GROUP/TUNA_GROUP(이미 있는 부위 그룹)에 흔한 생선/육류 몇 가지를
# 더한 것으로, 완벽한 목록일 필요는 없다(지침 8번 원칙).
PROTEIN_INGREDIENTS: set[str] = PORK_GROUP | BEEF_GROUP | TUNA_GROUP | {
    "고등어", "갈치", "꽁치", "삼치", "연어", "고등어자반",
    "새우", "오징어", "조개", "홍합", "굴", "낙지", "문어", "게",
    "닭고기", "오리고기", "닭가슴살", "닭다리살", "닭안심",
}


def _is_protein(name: str) -> bool:
    """이 재료명이 육류/생선(단백질 재료)로 볼 수 있는지 (부분일치)."""
    return any(p in name for p in PROTEIN_INGREDIENTS)


def _has_protein_match(user_norm: list[str], recipe_norm: list[str]) -> bool:
    """
    유저가 보유한 단백질 재료(고등어/갈치/참치/돼지고기 등) 중 하나라도 이 레시피의 재료와
    실제로 매칭되는지 확인한다. 겹침 "개수"와 별개로, "단백질을 실제로 쓰는 레시피인가"만
    True/False로 판단하는 용도다.
    """
    protein_user = [u for u in user_norm if _is_protein(u)]
    if not protein_user:
        return False
    return any(ingredients_match(u, ri) for u in protein_user for ri in recipe_norm)


# 2026-07 9차 개정(#77): 8차(단백질 매칭)까지 반영해도 여전히 남는 문제 - "메뉴명에 그대로
# 박혀있는 재료"조차 없는데 추천되는 경우다. 실사용 확인: "두부샐러드 메밀김밥"은 두부·계란
# 등은 겹치지만 정작 이름의 "메밀"(김밥을 싸는 재료 자체)이 보유 재료에 없고, "오징어불고기
# 김밥"은 이름의 "오징어"가 보유 재료에 없다 - 둘 다 그 요리를 그 요리이게 하는 핵심 재료가
# 없는데도, 다른 잡다한 재료 겹침(overlap)·단백질 매칭(has_protein_match, 다른 부위 고기로
# 걸림)만으로 상위에 올라왔다. 메뉴명에 재료 이름이 그대로 들어있다는 것 자체가 "이 요리는
# 이 재료 없이는 성립하지 않는다"는 가장 확실한 신호이므로, 그 재료를 하나도 안 갖고 있으면
# "자격 미달(qualifies=False)"로 처리해서 다른 겹침이 아무리 많아도 뒤로 민다.
def _find_core_ingredients(menu_name: str, recipe_norm: list[str]) -> list[str]:
    """
    메뉴명(레시피 이름) 안에 그대로 포함된 재료명을 "핵심 재료"로 뽑는다
    (예: "오징어불고기김밥" -> "오징어", "메밀김밥" -> "메밀"). recipe_norm은 이미 조미료를
    걸러낸 랭킹용 재료 리스트이므로 여기서 다시 거를 필요는 없다. ingredients_match()와 같은
    이유로, 1글자 재료명(예: "배", "무")은 메뉴명에 우연히 포함될 위험이 커서 제외하고
    2글자 이상인 것만 인정한다.
    """
    name_clean = menu_name.replace(" ", "") if menu_name else ""
    return [ri for ri in recipe_norm if len(ri) >= 2 and ri in name_clean]


def _core_ingredients_satisfied(user_norm: list[str], core_ingredients: list[str]) -> bool:
    """
    메뉴명에서 핵심 재료가 하나도 안 뽑히면(대부분의 메뉴명은 재료명을 그대로 안 씀) 그냥
    통과시킨다 - 핵심 재료가 있을 때만 검사하는 게 목적이다.

    핵심 재료가 여러 개 뽑히면(예: "두부샐러드 메밀김밥" -> "두부", "메밀" 둘 다), 그 "전부"를
    유저가 보유하고 있어야 한다 - 처음엔 "최소 1개만 있어도 통과(any)"로 짰었는데, 그러면
    "두부"만 있고 "메밀"은 없어도 통과돼버려서, 정작 유저가 지적한 "메밀이 없다"는 문제를 못
    잡았다. 메뉴명이 두 재료를 나란히 이름에 넣었다는 건 "이 요리는 이 둘 다로 정의된다"는
    뜻이므로, 하나라도 없으면(예: 메밀) 이 요리는 성립하지 않는다고 본다(all).
    """
    if not core_ingredients:
        return True
    return all(
        any(ingredients_match(u, ci) for u in user_norm)
        for ci in core_ingredients
    )

# 거의 모든 레시피에 들어가는 기본 조미료: 매칭 점수 계산에서 제외한다.
# (안 그러면 "소금·마늘·참기름 겹침" 때문에 실제로는 무관한 레시피가 상위로 올라온다)
STAPLE_SEASONINGS = {
    "소금", "설탕", "간장", "참기름", "마늘", "대파", "파", "후추",
    "식용유", "고춧가루", "깨", "통깨", "물엿", "요리당", "식초", "물",
}


# 유저가 등록한 레시피(recipes.source_api == "user")는 검증되지 않은 데이터라서,
# 다른 유저들의 추천(좋아요)이 이 개수 이상 쌓이기 전까지는 AI 추천 후보에 넣지 않는다.
USER_RECIPE_MIN_LIKES = 100


def is_staple(name: str) -> bool:
    """부분 일치로 확인한다 (예: "저염간장"도 "간장"이 포함돼 있으면 조미료로 취급)."""
    return any(staple in name for staple in STAPLE_SEASONINGS)


def normalize_ingredient(name: str) -> str:
    return SYNONYM_MAP.get(name, name)


def ingredients_match(a: str, b: str) -> bool:
    """
    두 재료명(둘 다 normalize_ingredient()를 거친 값이어야 함)이 "같은 재료"로 볼 수 있는지
    판단한다. 완전히 같으면 항상 매칭이고, 부분 일치(포함 관계)는 짧은 쪽이 최소 2글자 이상일
    때만 인정한다.

    왜 필요한가(#71): "배추"를 보유 재료로 입력했더니, 레시피의 "배"(배추가 아니라 과일
    "배") 하나 때문에 매칭이 잡히는 문제가 실사용에서 발견됐다 - "배"가 "배추"/"양배추"의
    부분 문자열이기 때문이다(배추 = 배 + 추). 이 때문에 실제로는 배·과일이 전혀 안 들어간
    "냉잡채"가 진짜 관련있는 참치 요리보다 순위가 높게 나오는 결과로 이어졌다. 한글은 음절
    하나가 이미 뜻이 있는 글자라서(배, 콩, 무, 김 등), 1글자짜리는 완전히 같은 단어일 때만
    매칭을 인정하고, 부분 포함으로는 인정하지 않는다. "고추"/"고추장"처럼 2글자 이상인
    부분일치 오매칭(가공식품이 원재료 이름을 포함하는 경우)은 이 규칙으로는 못 막는다 -
    별도로 논의가 필요한, 더 큰 작업이다.

    2026-07 8차 개정(#74): 부분일치로도 못 잡는 경우가 하나 더 있다 - "삼겹살"과 "돼지고기"
    처럼 아예 다른 단어인 부위명. 이런 건 PORK_GROUP/BEEF_GROUP/TUNA_GROUP 같은 그룹으로
    따로 관리하고, 같은 그룹에 속하면(대체 가능한 같은 고기/생선으로 보고) 매칭으로 인정한다.
    """
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 2 and shorter in longer:
        return True
    return _same_ingredient_group(a, b)


def get_user_profile(cur, user_id: int) -> dict | None:
    cur.execute("""
        SELECT id, gender, age_group, allergy, health_goal, purpose,
               cooking_level, supplements, household_size, novelty_pref, cooking_tools,
               medical_conditions
        FROM users WHERE id = ?
    """, (user_id,))
    row = cur.fetchone()
    if row is None:
        return None

    columns = ["id", "gender", "age_group", "allergy", "health_goal", "purpose",
               "cooking_level", "supplements", "household_size", "novelty_pref", "cooking_tools",
               "medical_conditions"]
    return dict(zip(columns, row))


def _has_placeholder_nutrition(calorie, nutrients_json: str | None) -> bool:
    """
    실사용 확인(#84): 공공데이터(식약처 조리식품 레시피DB) 원본 자체에 칼로리/탄수화물/
    단백질/지방/나트륨 5개 필드가 전부 "1"처럼 결측치 표기로 보이는 값만 들어있는 레시피가
    실제로 있다(전체 1146개 중 2개 확인 - "클럽 샌드위치": 식빵/마요네즈/달걀/닭가슴살/
    토마토/치즈가 들어가는 정상적인 메뉴인데도, 원본 API 응답 자체가
    INFO_ENG=INFO_CAR=INFO_PRO=INFO_FAT=INFO_NA=1이다 - 원본 JSON 샘플을 직접 열어서
    확인했고, 우리 쪽 파싱 문제가 아니라 원본 데이터 자체의 결측치 표기 오류였다).
    이런 레시피를 그대로 후보에 두면 "칼로리 1kcal"라는 잘못된 값 때문에 다이어트 목표
    정렬(칼로리 낮은 순 동점 처리)에서 실제 근거 없이 항상 이겨버리는 문제가 생기므로,
    애초에 추천 후보에서 제외한다.
    """
    try:
        nutrients = json.loads(nutrients_json) if nutrients_json else {}
    except (json.JSONDecodeError, TypeError):
        nutrients = {}

    values = [calorie, nutrients.get("carbs_g"), nutrients.get("protein_g"),
              nutrients.get("fat_g"), nutrients.get("sodium_mg")]
    try:
        return all(v is not None and float(v) <= 5 for v in values)
    except (TypeError, ValueError):
        return False


def get_candidate_recipes(cur, profile: dict) -> list[dict]:
    """
    모든 레시피를 가져와서, 사용자의 알레르기 목록에 걸리는 레시피는 제외한다.
    - status != 'approved'인 레시피(관리자 승인 대기중인 유저 레시피)는 제외한다.
    - 유저가 등록한 레시피(source_api == "user")는 추천(좋아요)이 USER_RECIPE_MIN_LIKES
      이상 쌓인 것만 후보에 포함한다 (검증 안 된 데이터가 그대로 추천되는 것을 막기 위함).
    - 영양정보 5개 필드가 전부 결측치 표기(예: 전부 1)로 보이는 레시피는 제외한다(#84).

    성능(N+1 개선): 원래는 레시피마다 recipe_likes/recipe_tags를 개별 SELECT했는데(최대
    1,148개 레시피 x 최대 3쿼리), 레시피 목록을 먼저 다 가져온 뒤 recipe_id IN (...)으로
    좋아요 개수·알레르기 태그·영양군 태그를 한 번씩만 조회해서 딕셔너리로 인덱싱해두고
    루프 안에서는 그 딕셔너리만 참조한다. 필터링/제외 판단 로직 자체는 그대로다.
    """
    user_allergies = set(a.strip() for a in profile.get("allergy", "").split(",") if a.strip())

    cur.execute(
        "SELECT id, menu_name, cook_method, category, calorie, nutrients_json, "
        "steps_json, youtube_url, image_url, source_api, submitted_by FROM recipes WHERE status = 'approved'"
    )
    recipes = cur.fetchall()

    recipe_ids = [row[0] for row in recipes]
    if not recipe_ids:
        return []
    placeholders = ",".join("?" for _ in recipe_ids)

    # 유저 등록 레시피(source_api == "user")만 좋아요 개수가 필요하다.
    user_recipe_ids = [row[0] for row in recipes if row[9] == "user"]
    like_counts: dict[int, int] = {}
    if user_recipe_ids:
        like_placeholders = ",".join("?" for _ in user_recipe_ids)
        cur.execute(
            f"SELECT recipe_id, COUNT(*) FROM recipe_likes WHERE recipe_id IN ({like_placeholders}) "
            "GROUP BY recipe_id",
            user_recipe_ids
        )
        like_counts = dict(cur.fetchall())

    cur.execute(
        f"SELECT recipe_id, tag_value FROM recipe_tags WHERE recipe_id IN ({placeholders}) "
        "AND tag_type = 'allergy'",
        recipe_ids
    )
    allergens_by_recipe: dict[int, set[str]] = {}
    for recipe_id, tag_value in cur.fetchall():
        allergens_by_recipe.setdefault(recipe_id, set()).add(tag_value)

    cur.execute(
        f"SELECT recipe_id, tag_value FROM recipe_tags WHERE recipe_id IN ({placeholders}) "
        "AND tag_type = 'nutrition_group'",
        recipe_ids
    )
    # 레시피당 nutrition_group 태그는 1개뿐이라, 원래 cur.fetchone()과 동일하게 처음 값만 쓴다.
    nutrition_group_by_recipe: dict[int, str] = {}
    for recipe_id, tag_value in cur.fetchall():
        nutrition_group_by_recipe.setdefault(recipe_id, tag_value)

    candidates = []
    for (recipe_id, menu_name, cook_method, category, calorie, nutrients_json, steps_json,
         youtube_url, image_url, source_api, submitted_by) in recipes:
        if source_api == "user" and like_counts.get(recipe_id, 0) < USER_RECIPE_MIN_LIKES:
            continue

        if _has_placeholder_nutrition(calorie, nutrients_json):
            continue

        # 사용자 알레르기와 겹치는 게 있으면 이 레시피는 제외
        recipe_allergens = allergens_by_recipe.get(recipe_id, set())
        if user_allergies & recipe_allergens:
            continue

        nutrition_group = nutrition_group_by_recipe.get(recipe_id, "미분류")

        candidates.append({
            "id": recipe_id,
            "menu_name": menu_name,
            "cook_method": cook_method,
            "category": category,
            "calorie": calorie,
            "nutrition_group": nutrition_group,
            "nutrients_json": nutrients_json,
            "steps_json": steps_json,
            "youtube_url": youtube_url,
            "image_url": image_url,
            # [#95] 구매 링크에 누구 키를 쓸지 판단하는 데 필요하다(shopping_agent 참고).
            "source_api": source_api,
            "submitted_by": submitted_by,
        })

    return candidates


def get_alternative_recipe(cur, profile: dict, current_recipe_id: int, nutrition_group: str) -> dict | None:
    """"이 메뉴가 싫다면?" 버튼(2026-07-21, #req6) - 재료 겹침은 보지 않고, 같은 영양군
    (nutrition_group)에 속하면서 칼로리가 가장 비슷한 다른 레시피 하나를 대신 추천한다.
    get_candidate_recipes()를 그대로 재사용해서 알레르기/승인 여부 등 안전 필터는 똑같이
    적용된다 - "재료와 무관해도 된다"는 요청이지 안전 필터까지 건너뛰라는 뜻은 아니다."""
    candidates = get_candidate_recipes(cur, profile)
    current = next((c for c in candidates if c["id"] == current_recipe_id), None)
    same_group = [
        c for c in candidates
        if c["nutrition_group"] == nutrition_group and c["id"] != current_recipe_id
    ]
    if not same_group:
        return None
    current_calorie = current["calorie"] if current and current["calorie"] is not None else None
    if current_calorie is not None:
        same_group.sort(key=lambda c: abs((c["calorie"] or 0) - current_calorie))
    else:
        same_group.sort(key=lambda c: c["menu_name"])
    return same_group[0]


def get_recipe_by_id(cur, recipe_id: int) -> dict | None:
    """
    즐겨찾기 상세보기처럼, AI 추천 흐름을 다시 타지 않고 레시피 하나를 그대로 불러올 때 쓴다.
    get_candidate_recipes()가 만드는 dict와 같은 모양으로 반환해서, 결과 카드 렌더링 함수를
    그대로 재사용할 수 있게 한다.
    """
    cur.execute(
        "SELECT id, menu_name, cook_method, category, calorie, nutrients_json, "
        "steps_json, youtube_url, image_url, source_api, submitted_by FROM recipes WHERE id = ?",
        (recipe_id,)
    )
    row = cur.fetchone()
    if row is None:
        return None
    (recipe_id, menu_name, cook_method, category, calorie, nutrients_json, steps_json,
     youtube_url, image_url, source_api, submitted_by) = row

    cur.execute(
        "SELECT tag_value FROM recipe_tags WHERE recipe_id = ? AND tag_type = 'nutrition_group'",
        (recipe_id,)
    )
    nutrition_row = cur.fetchone()
    nutrition_group = nutrition_row[0] if nutrition_row else "미분류"

    return {
        "id": recipe_id,
        "menu_name": menu_name,
        "cook_method": cook_method,
        "category": category,
        "calorie": calorie,
        "nutrition_group": nutrition_group,
        "nutrients_json": nutrients_json,
        "steps_json": steps_json,
        "youtube_url": youtube_url,
        "image_url": image_url,
        "ingredient_overlap": 0,
        # [#95] 이 레시피가 유저 등록 레시피인지, 누가 등록했는지 - 구매 링크에 누구 키를
        # 쓸지 판단할 때(shopping_agent.get_shopping_key_for_recipe) 필요하다.
        "source_api": source_api,
        "submitted_by": submitted_by,
    }


def search_all_recipes(
    cur, keyword: str = "", limit: int = 20, offset: int = 0, category: str | None = None
) -> list[dict]:
    """
    "레시피 찾아보기" 화면에서 쓴다. 프로필/알레르기 필터 없이, 승인된(approved) 레시피 전체를
    메뉴명으로 검색한다 (keyword가 비어있으면 전체를 메뉴명 순으로).
    category를 주면("전체" 또는 None이 아니면) 해당 분류로도 좁혀서 찾는다 (#58 필터 칩).
    """
    conditions = ["status = 'approved'"]
    params: list = []
    if keyword.strip():
        conditions.append("menu_name LIKE ?")
        params.append(f"%{keyword.strip()}%")
    if category and category != "전체":
        conditions.append("category = ?")
        params.append(category)
    where_sql = " AND ".join(conditions)

    cur.execute(
        f"SELECT id, menu_name, category, calorie FROM recipes WHERE {where_sql} "
        f"ORDER BY menu_name LIMIT ? OFFSET ?",
        (*params, limit, offset)
    )
    rows = cur.fetchall()
    return [{"id": r[0], "menu_name": r[1], "category": r[2], "calorie": r[3]} for r in rows]


def count_all_recipes(cur, keyword: str = "", category: str | None = None) -> int:
    conditions = ["status = 'approved'"]
    params: list = []
    if keyword.strip():
        conditions.append("menu_name LIKE ?")
        params.append(f"%{keyword.strip()}%")
    if category and category != "전체":
        conditions.append("category = ?")
        params.append(category)
    where_sql = " AND ".join(conditions)

    cur.execute(f"SELECT COUNT(*) FROM recipes WHERE {where_sql}", params)
    return cur.fetchone()[0]


def get_recipe_categories(cur) -> list[str]:
    """
    "레시피 찾아보기" 필터 칩에 쓸 분류 목록을 실제 데이터에서 뽑아온다 (#58).
    분류 이름을 임의로 추측해서 하드코딩하지 않고, 실제 등록된(approved) 레시피에 있는
    category 값만, 많이 쓰이는 순으로 반환한다.
    """
    cur.execute(
        "SELECT category, COUNT(*) AS c FROM recipes "
        "WHERE status = 'approved' AND category IS NOT NULL AND category != '' "
        "GROUP BY category ORDER BY c DESC"
    )
    return [row[0] for row in cur.fetchall()]


# 최소 이 비율(조미료 제외 재료 기준) 이상은 맞아야 "쓸만한 후보"로 인정한다 (2026-07 4차 개정,
# A안). 실측(#69): 보유 재료를 실제로 많이 쓰는 메인요리들은 대개 0.3~0.8 사이였고, 이 문턱을
# 낮게(0.2) 잡아도 걸러지지 않았다. 반면 이 문턱이 없으면 "재료 20개 중 2개만 우연히 겹치는"
# 대형 레시피가 순전히 개수(overlap)만으로 상위에 올라오는, 1차 개정 때 이미 한 번 겪었던
# 실패가 재발할 수 있다 - 그래서 반드시 이 하한선과 함께 써야 한다.
MIN_COVERAGE_RATIO_FLOOR = 0.2

# 2026-07 7차 개정(#73): 개수 비율(MIN_COVERAGE_RATIO_FLOOR)만으로 자격을 판단하면, "참치
# 100g"이 사실상 요리 전체인 초밥류처럼 재료가 10개 넘게 필요한 레시피에서, 유저가 그 핵심
# 재료 딱 1개만 갖고 있어도 "개수 비율"로는 20% 밑으로 떨어져 통째로 탈락해버리는 문제가
# 실측에서 발견됐다("소금없는 초밥" - 참치 100g, 전체 500g 중 20%인데 개수로는 1/9=11%라
# 탈락). 그래서 "개수 비율" 또는 "무게 비율(matched_weight ÷ 레시피 전체 재료 무게)" 중
# 하나만 넘어도 자격을 준다 - 재료가 많이 필요한 레시피라도, 유저가 가진 재료가 무게 기준
# 핵심 재료라면 순위 경쟁에는 낄 수 있게 한다.
WEIGHT_RATIO_FLOOR = 0.2


# 2026-07 6차 개정(B안): 겹침 개수만 보면, 원래 재료 수가 적고 조리 단계도 짧은 반찬류가
# "동점"일 때 조리 단계 적은 순 규칙 때문에 구조적으로 계속 유리해진다. 그래서 고등어·갈치처럼
# 메인요리 재료를 많이 들고 있어도 계속 반찬(예: 토마토제철나물 샐러드)이 이겨버리는 문제가
# 실사용에서 발견됐다 - "겹침 개수"는 고쳤지만 "이게 식사로 말이 되는 추천인가"는 전혀 다른
# 축의 문제라서 A안(overlap 랭킹)만으로는 못 막는다.
# 카테고리를 3단계로 나눠서, 같은 자격(qualifies) 안에서는 이 순서를 겹침 개수보다 먼저 본다:
#   0단계(우선) - 일품/밥/국&찌개: 그 자체로 한 끼가 되는 메인성 카테고리
#   1단계 - 반찬/기타: 0단계에 자격 있는 후보가 하나도 없을 때만 이 단계에서 고른다
#   2단계(항상 최후) - 후식: 아무리 겹침이 많아도 "오늘의 한 끼" 추천으로는 마지막 순위
MAIN_CATEGORIES = {"일품", "밥", "국&찌개"}
DESSERT_CATEGORY = "후식"


def _category_tier(category: str | None) -> int:
    """카테고리를 랭킹 우선순위 단계(0=메인성, 1=반찬/기타, 2=후식)로 바꾼다."""
    if category == DESSERT_CATEGORY:
        return 2
    if category in MAIN_CATEGORIES:
        return 0
    return 1


# recipe_ingredients 테이블(농림수산식품교육문화정보원 데이터)에는 recipe_tags와 달리
# 실제 수량(amount/unit)이 있다. 이걸로 "겹치는 재료가 주재료급(수십~수백g)인지, 고명·향신용
# (몇 g 안 되는)인지"를 구분해서 랭킹에 반영한다 (2026-07 7차 개정, #73 - 겹침 "개수"는 같아도
# 그 안에 진짜 주재료가 들어있는지 여부를 가려달라는 요청으로 추가됨).
# g 단위가 아니거나(개/장/Ts/인분 등) 수량 자체가 없는 행은 정확한 환산이 어려우므로 임의의
# 작은 기본값을 쓴다 - 환산표를 완벽하게 만들 필요는 없다는 원칙(지침 8번)과 같은 이유다.
DEFAULT_UNIT_WEIGHT = 10.0

# recipe_ingredients는 recipe_tags와는 다른 원본 데이터라서 파싱 찌꺼기 패턴도 다르다.
# 예: "참치(캔"+"30g)"처럼 괄호 안에서 잘못 쪼개지거나, "[" 처럼 대괄호만 단독으로 남거나,
# 순수 숫자+단위 조각만 남는 경우가 실제 DB에서 확인됐다. 재료명에 아무 한글도 없거나 숫자가
# 섞여 있으면 진짜 재료명이 아니라 파싱 찌꺼기로 보고 건너뛴다.
_HANGUL_RE = re.compile(r"[가-힣]")
_DIGIT_RE = re.compile(r"[0-9]")


def _is_valid_ingredient_name(name: str) -> bool:
    return bool(name) and bool(_HANGUL_RE.search(name)) and not _DIGIT_RE.search(name)


def _get_weighted_recipe_ingredients_from_rows(rows: list[tuple]) -> list[tuple[str, float]]:
    """
    이 레시피의 (정리된 재료명, 수량가중치) 목록을 만든다. 조미료는 제외한다(랭킹용이라 -
    3원칙과 같은 이유, 화면 표시용 계산은 그대로 recipe_tags 기준을 쓰므로 영향 없음).
    같은 재료명이 여러 번 나오면(예: 냉잡채의 "간장" 2번) 수량을 합친다.

    rows는 recipe_ingredients의 (name, amount, unit) 행들 - score_by_ingredients()에서
    레시피마다 개별 조회하는 대신 배치로 미리 가져온 결과를 그대로 넘겨받기 위해, 조회
    부분을 _get_weighted_recipe_ingredients()에서 분리했다.
    """
    weights: dict[str, float] = {}
    for raw_name, amount, unit in rows:
        name = clean_ingredient_name(raw_name or "")
        if not _is_valid_ingredient_name(name) or is_staple(name):
            continue
        name_norm = normalize_ingredient(name)
        weight = amount if (unit == "g" and isinstance(amount, (int, float))) else DEFAULT_UNIT_WEIGHT
        weights[name_norm] = weights.get(name_norm, 0.0) + weight
    return list(weights.items())


def _get_weighted_recipe_ingredients(cur, recipe_id: int) -> list[tuple[str, float]]:
    """레시피 하나만 필요한 호출부(예: 배치 조회가 필요 없는 단건 조회)용 - 그대로 조회해서 넘긴다."""
    cur.execute(
        "SELECT name, amount, unit FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,)
    )
    return _get_weighted_recipe_ingredients_from_rows(cur.fetchall())


def _count_matched_weight(user_norm: list[str], recipe_weighted: list[tuple[str, float]]) -> float:
    """
    _count_matched_ingredients()와 같은 1:1 그리디 매칭 방식으로, 이번엔 "개수"가 아니라
    "겹치는 재료들의 수량 합"을 구한다. 예를 들어 참치 50g이 매칭되면 50을, 깻잎 1g이
    매칭되면 1을 더한다 - 겹침 "개수"는 같아도(예: 3개), 그 3개가 주재료급(고기·생선
    수십g)인지 고명급(향신채 1~5g)인지를 구분해서 순위에 반영할 수 있다.
    """
    used_idx = set()
    total_weight = 0.0
    for u in user_norm:
        for idx, (ri, w) in enumerate(recipe_weighted):
            if idx in used_idx:
                continue
            if ingredients_match(u, ri):
                used_idx.add(idx)
                total_weight += w
                break
    return total_weight


def _count_matched_ingredients(user_norm: list[str], recipe_norm: list[str]) -> int:
    """
    유저 재료와 레시피 재료를 1:1로만 짝짓는 그리디 매칭으로 "진짜 겹치는 개수"를 센다.

    왜 필요한가(2026-07 5차 개정, #70): 4차 개정에서 "레시피 재료 기준으로 순회"해서 유저 쪽
    이중 카운팅("배추"+"양배추"가 레시피의 "양배추" 하나를 2번 세는 것)은 고쳤는데, 그 반대
    방향의 인플레이션은 그대로 남아 있었다 - 유저가 "고추" 하나만 입력해도, 레시피에 "홍고추",
    "청고추", "고추장"처럼 "고추"를 포함한 태그가 여러 개 있으면 전부 다 겹침으로 잡혔다.
    실사용 보고: 보유 재료에 골뱅이·과일이 전혀 없는데 "골뱅이과일무침"이 "보유재료 7개 활용"
    으로 추천됨 - 실제로는 "고추" 하나가 홍고추/청고추/고추장 3곳에 중복으로 걸리고, 진짜
    관련있는 재료는 당근 하나뿐이었다. 같은 문제가 반대로도 있었다 - 한 레시피 안에 같은
    재료가 "속재료: 삶은 밤고구마", "버터크림재료: 삶은 자색고구마"처럼 여러 번 다르게
    적혀 있으면(원본 데이터 특성, #68 참고), 유저의 "고구마" 하나가 그 여러 태그에 전부
    걸려서 겹침 개수가 부풀려졌다.

    해결: 유저 재료 하나는 레시피 재료 하나에만, 레시피 재료 하나도 유저 재료 하나에만
    쓸 수 있게(1:1) 그리디로 짝짓는다. 이러면 "고추"는 셋 중 어느 하나에만 매칭되고 나머지는
    매칭 안 된 것으로 처리되며, 중복 태깅된 "고구마"도 딱 1개로만 잡힌다.

    매칭 판단 자체는 ingredients_match()를 쓴다(#71) - 단순 부분일치만 쓰면 "배추"가
    "배"(과일 배)에 걸리는 것처럼 전혀 다른 재료가 우연히 겹치는 문제가 있어서다.
    """
    used_recipe_idx = set()
    overlap = 0
    for u in user_norm:
        for idx, ri in enumerate(recipe_norm):
            if idx in used_recipe_idx:
                continue
            if ingredients_match(u, ri):
                used_recipe_idx.add(idx)
                overlap += 1
                break
    return overlap


def score_by_ingredients(cur, candidates: list[dict], user_ingredients: list[str]) -> list[dict]:
    """
    "보유 재료를 얼마나 잘 활용하는 레시피인지"를 기준으로 정렬한다.
    포함 관계(부분 일치)로 비교한다 (예: 사용자가 "두부"라고 입력해도 "연두부" 태그와 겹치는 것으로 인정).

    이 정렬 기준은 지금까지 아홉 번 수정을 거쳤다:
    1) 처음에는 겹치는 재료 개수(ingredient_overlap)만으로 정렬했는데, 그러면 재료가
       10개 넘게 필요한 레시피가 "3개 겹침"이라는 이유만으로, 재료 4개짜리에 "3개 겹침"인
       레시피보다 앞에 오는 문제가 있었다.
    2) "부족한 재료 개수(missing_count)가 적은 순"으로 바꿨는데, 반대로 재료가 1~2개짜리인
       아주 단순한 레시피가 "보유 재료를 0개 활용"하면서도 missing_count가 작다는 이유만으로
       최상단에 뽑히는 문제가 있었다.
    3) "coverage_ratio(겹침/전체 필요재료수) 우선"으로 바꿨는데, 이번엔 반찬류(피클·장아찌 등
       원래 재료가 2~3개뿐인 요리)가 그 2~3개만 맞아도 100% 비율이 나와 버려서, 보유 재료를
       잔뜩 갖고 있어도 사소한 반찬만 계속 추천되는 문제가 실사용에서 발견됐다(#69).
    4) "겹치는 재료 개수(overlap)"를 다시 1순위로 쓰되, MIN_COVERAGE_RATIO_FLOOR 미만인
       후보는 "자격 미달"로 분류해서 뒤로 미루도록 바꿨다(A안). 그런데 이때 겹침 개수 계산을
       "레시피 재료 기준"으로 순회하도록 고쳤을 뿐, 유저 재료 하나가 레시피의 여러 유사 태그에
       동시에 매칭되는 반대 방향 인플레이션은 남아 있었다.
    5) 유저 재료 "고추" 하나가 레시피의 "홍고추"/"청고추"/"고추장" 세 곳에 전부 걸려서,
       실제로는 무관한 "골뱅이과일무침"이 "보유재료 7개 활용"으로 뜨는 문제가 실사용에서
       발견됐다(#70). `_count_matched_ingredients()`의 1:1 그리디 매칭으로 교체해서, 유저
       재료 하나·레시피 재료 하나가 각각 최대 1번만 겹침으로 잡히게 했다.
    6) 레시피 재료 "배"(과일)가 유저의 "배추"/"양배추"에 1글자 부분일치로 걸려서, 전혀
       무관한 "냉잡채"가 진짜 참치 요리보다 순위가 높게 나오는 문제가 발견됐다(#71).
       `ingredients_match()`를 도입해 부분일치는 짧은 쪽이 2글자 이상일 때만 인정하게 했다.
    7) 겹침 개수/매칭 자체는 정확해졌는데, 반찬류는 원래 재료가 적고 조리단계도 짧아서
       "겹침 개수" 동점 시 구조적으로 계속 메인요리를 이겼다 - 생선·고기를 잔뜩 들고 있어도
       작은 반찬(예: 토마토제철나물 샐러드)이 계속 1위로 뜨는 문제(#72). category_tier(B안,
       일품/밥/국&찌개 우선)를 추가했다. 그런데 카테고리를 메인성으로 맞춰도, 그 메인요리가
       "정말 유저가 가진 재료(예: 생선)를 주재료로 쓰는지"는 여전히 안 보고 있었다 - 겹침
       "개수"는 두부·양배추·깻잎(전부 소량) 3개나, 참치 50g 1개나 똑같이 셌기 때문이다(#73).
       recipe_ingredients 테이블의 실제 수량(g)으로 matched_weight를 계산해서, 겹침 개수가
       같을 때는 그 겹침이 주재료급인 레시피를 고명급인 레시피보다 우선하도록 했다. 이 과정에서
       또 다른 문제가 드러났다 - 자격(qualifies) 판단 자체가 "개수 비율"만 보다 보니, 재료가
       10개 넘게 필요한 레시피에서 유저가 그 중 진짜 핵심 재료(예: 참치 100g, 요리 전체의
       핵심) 딱 1개만 갖고 있어도 "개수 비율"로는 20% 밑으로 떨어져 통째로 탈락했다(예:
       "소금없는 초밥"). 그래서 자격 기준을 "개수 비율 또는 무게 비율(weight_ratio) 중
       하나만 넘어도 통과"로 바꿨다.
    8) (2026-07, #76) 카테고리·겹침·가중치가 다 정확해졌는데도, 실사용에서 새로운 문제가
       발견됐다 - 고등어·갈치·참치·전지(돼지고기)를 보유했는데, 상위 3개 후보가 전부
       두부·양배추·깻잎 같은 채소만 매칭되고 단백질(육류·생선)은 하나도 안 썼다. 겹침
       "개수"만 보면 채소 4개 겹침이 단백질 1개 겹침보다 항상 이기기 때문이다(예: 두부+
       양배추+깻잎+배추 겹침 4개 vs 참치 겹침 1개 - 후자가 훨씬 "그 재료로 만든 요리"라는
       실감이 크지만 순위는 밀림). has_protein_match를 category_tier 다음 우선순위로 추가해서,
       보유 단백질을 실제로 쓰는 레시피가 채소만 겹치는 레시피보다 항상 앞서게 했다.
    9) (2026-07, #77) 단백질 매칭까지 반영해도, "메뉴명에 그대로 박힌 재료"조차 없는 요리가
       여전히 추천됐다 - "두부샐러드 메밀김밥"은 이름의 "메밀"이 보유 재료에 없고, "오징어
       불고기김밥"은 이름의 "오징어"가 보유 재료에 없는데도, 다른 재료 겹침·단백질 매칭(다른
       부위 고기로 걸림)만으로 상위 3개에 올라왔다. 메뉴명에 재료 이름이 그대로 들어있다는 것
       자체가 "이 재료 없이는 이 요리가 성립하지 않는다"는 가장 확실한 신호이므로,
       core_ingredients(메뉴명에서 뽑은 핵심 재료)를 모두 갖고 있지 않으면 qualifies 자체를
       False로 만들어서 다른 겹침이 아무리 많아도 뒤로 밀리게 했다. 처음엔 "핵심 재료 중
       최소 1개만 있어도 통과"로 짰다가, "두부샐러드 메밀김밥"이 "두부"는 있고 "메밀"은 없는데도
       통과되는 걸 발견해서 "전부 다 있어야 통과"로 바로 고쳤다 - 메뉴명이 두 재료를 나란히
       썼다는 건 "이 요리는 이 둘 다로 정의된다"는 뜻이기 때문이다.

    추천 원칙(2026-07 9차 개정):
      0원칙 - 자격 미달은 무조건 뒤로 밀린다. 자격 조건은 두 가지를 "모두" 만족해야 한다:
              (a) coverage_ratio가 MIN_COVERAGE_RATIO_FLOOR 이상이거나 weight_ratio가
              WEIGHT_RATIO_FLOOR 이상 (개수 또는 무게 기준으로 충분히 겹침), 그리고
              (b) core_ok(메뉴명에서 뽑은 핵심 재료가 있다면 그 "전부"를 보유) - 핵심
              재료가 아예 없는 메뉴명이면 (b)는 자동 통과(#77).
      0.5원칙 - 자격이 같으면 category_tier(0=일품/밥/국&찌개, 1=반찬/기타, 2=후식)를 먼저
              본다 - 메인성 카테고리가 반찬/후식보다 항상 우선한다(B안, #72).
      0.7원칙 - 카테고리 단계까지 같으면, has_protein_match(보유한 육류·생선을 실제로 쓰는지)를
              본다 - 단백질을 쓰는 레시피가 채소/두부만 겹치는 레시피보다 항상 우선한다(#76).
      1원칙 - 거기까지 같으면, 보유 재료와 실제로 겹치는 재료 "개수"
              (ingredient_overlap, 1:1 매칭 기준)를 우선한다.
      1.5원칙 - 겹침 개수까지 같으면, matched_weight(겹친 재료들의 실제 수량 합, g 기준)가
              큰 쪽을 우선한다 - "겹침 3개"가 참치 50g인지 깻잎 3g인지를 구분한다(#73).
      2원칙 - 그래도 같으면, 조리 순서(steps_json)가 적은(간단한) 레시피를 우선한다.
      3원칙 - 화면에 보여주는 "재료"/"부족한 재료"/"보유 재료 사용률"은 조미료까지 포함해서
              무조건 정확하게 표기한다 (이건 이 함수가 아니라 substitution_agent.py의
              get_missing_ingredients()/get_ingredient_coverage()에서 처리한다 - 그 두 함수는
              "표시용"이라 조미료를 안 걸러내고, 이 함수는 "랭킹용"이라 조미료 노이즈를 걸러낸다).

    참고(아직 미해결): "고추"가 "고추장"(전혀 다른 가공식품)에도 부분일치로 걸리는 것 자체는
    이 1:1 매칭으로도 완전히 막지 못한다(여전히 후보 중 하나로는 매칭될 수 있음). 다만 최소
    1개로 제한되므로 예전처럼 한 단어가 여러 개로 부풀려지는 문제는 없다. 이 부분일치 규칙
    자체를 더 엄격하게(예: 가공식품 접미사 제외) 바꾸는 건 더 큰 작업이라 별도로 논의 필요.

    user_ingredients가 비어있으면 정렬하지 않고 그대로 반환한다.
    """
    if not user_ingredients:
        for c in candidates:
            c["ingredient_overlap"] = 0
            c["missing_count"] = 0
            c["coverage_ratio"] = 0.0
            c["qualifies"] = False
            c["category_tier"] = _category_tier(c.get("category"))
            c["matched_weight"] = 0.0
            c["weight_ratio"] = 0.0
            c["has_protein_match"] = False
            c["core_ingredients"] = []
            c["core_ok"] = True
        return candidates

    user_norm = [
        normalize_ingredient(u.strip()) for u in user_ingredients
        if u.strip() and not is_staple(u.strip())
    ]

    # 성능(N+1 개선): 원래는 후보 레시피마다 recipe_tags(ingredient)/recipe_ingredients를
    # 개별 SELECT했다(최대 1,148개 x 2쿼리). 후보 id를 모아 recipe_id IN (...)으로 한 번씩만
    # 조회해서 딕셔너리로 인덱싱해두고, 아래 루프에서는 그 딕셔너리만 참조한다. 매칭/점수
    # 계산 로직(1:1 그리디 매칭, 가중치 계산 등) 자체는 그대로다.
    candidate_ids = [c["id"] for c in candidates]
    ingredient_tags_by_recipe: dict[int, list[str]] = {}
    weighted_rows_by_recipe: dict[int, list[tuple]] = {}
    if candidate_ids:
        placeholders = ",".join("?" for _ in candidate_ids)

        cur.execute(
            f"SELECT recipe_id, tag_value FROM recipe_tags WHERE recipe_id IN ({placeholders}) "
            "AND tag_type = 'ingredient'",
            candidate_ids
        )
        for recipe_id, tag_value in cur.fetchall():
            ingredient_tags_by_recipe.setdefault(recipe_id, []).append(tag_value)

        cur.execute(
            f"SELECT recipe_id, name, amount, unit FROM recipe_ingredients "
            f"WHERE recipe_id IN ({placeholders})",
            candidate_ids
        )
        for recipe_id, name, amount, unit in cur.fetchall():
            weighted_rows_by_recipe.setdefault(recipe_id, []).append((name, amount, unit))

    scored = []
    for c in candidates:
        # 기본 조미료는 매칭 대상(랭킹)에서 제외 (거의 모든 레시피에 있어서 변별력이 없음).
        # 화면에 보여주는 "부족한 재료" 쪽은 조미료도 포함해서 따로 정확하게 계산한다 (3원칙).
        recipe_ingredients_norm = [
            normalize_ingredient(tag_value)
            for tag_value in ingredient_tags_by_recipe.get(c["id"], [])
            if not is_staple(tag_value)
        ]

        # 1:1 그리디 매칭으로 겹침 개수를 센다 (#70) - 유저 재료 하나·레시피 재료 하나가
        # 각각 최대 1번만 카운트된다.
        overlap = _count_matched_ingredients(user_norm, recipe_ingredients_norm)

        # 8차 개정(#76): 보유한 단백질(육류·생선)을 이 레시피가 실제로 쓰는지 - 겹침 개수와는
        # 별개로 True/False만 판단한다. 채소/두부만 겹치는 레시피와 구분하기 위함.
        has_protein_match = _has_protein_match(user_norm, recipe_ingredients_norm)

        # 이 레시피에 필요한 재료(조미료 제외) 중, 보유 재료로 채워지지 않는 개수
        total_needed = len(recipe_ingredients_norm)
        missing_count = max(total_needed - overlap, 0)
        coverage_ratio = (overlap / total_needed) if total_needed > 0 else 0.0

        # 7차 개정(#73): 겹침 "개수"가 같은 후보들 사이에서, 그 겹침이 주재료급(수량 많음)인지
        # 고명급(수량 적음)인지를 구분하는 가중치. recipe_tags가 아니라 수량 정보가 있는
        # recipe_ingredients 테이블을 배치 조회 결과에서 가져온다.
        recipe_weighted = _get_weighted_recipe_ingredients_from_rows(weighted_rows_by_recipe.get(c["id"], []))
        matched_weight = _count_matched_weight(user_norm, recipe_weighted)
        total_weight = sum(w for _, w in recipe_weighted)
        weight_ratio = (matched_weight / total_weight) if total_weight > 0 else 0.0

        # 9차 개정(#77): 메뉴명에 그대로 들어있는 재료("오징어불고기김밥"의 오징어, "메밀김밥"의
        # 메밀)는 이 요리를 규정하는 핵심 재료로 본다. 이게 하나도 없으면, 다른 재료가 아무리
        # 겹쳐도 자격 미달로 처리한다 - "그 요리의 정체성인 재료" 없이 추천하는 건 말이 안 된다.
        core_ingredients = _find_core_ingredients(c.get("menu_name", ""), recipe_ingredients_norm)
        core_ok = _core_ingredients_satisfied(user_norm, core_ingredients)

        # 자격(qualifies) 판단: 개수 비율 또는 무게 비율 중 하나만 넘어도 통과시킨다 - "참치
        # 100g"이 요리 전체의 핵심인 초밥류처럼, 재료가 많이 필요한 레시피에서 유저가 그 핵심
        # 재료 하나만 갖고 있어도 개수 비율로는 걸러지는 문제를 막기 위함(#73). 다만 메뉴명에
        # 박힌 핵심 재료(core_ok)가 없으면, 위 조건을 만족해도 자격 미달로 처리한다(#77).
        qualifies = (
            coverage_ratio >= MIN_COVERAGE_RATIO_FLOOR
            or weight_ratio >= WEIGHT_RATIO_FLOOR
        ) and core_ok

        # 2원칙: 조리 순서 개수 (적을수록 간단한 레시피). 단계 정보가 없거나 깨져있으면
        # "간단하다"고 함부로 추측하지 않고 큰 값을 줘서 뒤로 밀리게 한다.
        try:
            steps = json.loads(c.get("steps_json")) if c.get("steps_json") else []
            step_count = len(steps) if isinstance(steps, list) else 999
        except (json.JSONDecodeError, TypeError):
            step_count = 999

        scored.append({
            **c,
            "ingredient_overlap": overlap,
            "missing_count": missing_count,
            "coverage_ratio": coverage_ratio,
            "step_count": step_count,
            "qualifies": qualifies,
            "category_tier": _category_tier(c.get("category")),
            "matched_weight": matched_weight,
            "weight_ratio": weight_ratio,
            "has_protein_match": has_protein_match,
            "core_ingredients": core_ingredients,
            "core_ok": core_ok,
        })

    # 0원칙: 자격 미달(qualifies=False)은 전부 뒤로 밀린다.
    # 0.5원칙(2026-07 6차 개정, B안): 자격이 같으면, 카테고리 단계(category_tier)를 겹침
    #        개수보다 먼저 본다 - 일품/밥/국&찌개(0단계)가 반찬/기타(1단계)보다 항상 앞서고,
    #        후식(2단계)은 항상 맨 뒤다. 이래야 "겹침 개수"만으로 반찬이 메인요리를 이기는
    #        문제(#72)가 막힌다.
    # 0.7원칙(2026-07 8차 개정, #76): 카테고리 단계까지 같으면, has_protein_match(보유한
    #        육류·생선을 실제로 쓰는지)를 겹침 개수보다 먼저 본다 - 채소/두부 4개가 겹치는
    #        레시피가, 참치 1개만 겹치는 레시피를 항상 이기던 문제를 막는다.
    # 1원칙: 거기까지 같으면, 겹치는 개수(overlap)가 많은 순.
    # 1.5원칙(2026-07 7차 개정, #73): 겹침 개수까지 같으면, 그 겹침이 주재료급(수량 많음)인
    #        후보를 고명급(수량 적음)인 후보보다 우선한다(matched_weight). "겹침 3개"가 같아도
    #        참치 50g이 매칭된 레시피가 깻잎 1g만 매칭된 레시피보다 실제로는 더 그 재료를 살려
    #        쓰는 레시피이기 때문이다.
    # 2원칙: 그래도 같으면 조리 순서가 적은(간단한) 순.
    # 그 외 세부 동점 처리: 부족한 재료가 적은 순 -> 비율이 높은 순
    scored.sort(key=lambda c: (
        not c["qualifies"], c["category_tier"], not c["has_protein_match"],
        -c["ingredient_overlap"], -c["matched_weight"],
        c["step_count"], c["missing_count"], -c["coverage_ratio"]
    ))
    return scored


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 아까 저장한 테스트 프로필(user_id=2, 알레르기: 새우,땅콩)로 테스트
    test_user_id = 2
    profile = get_user_profile(cur, test_user_id)

    if profile is None:
        print(f"user_id={test_user_id} 프로필을 찾을 수 없습니다.")
    else:
        print(f"프로필: {profile}\n")
        candidates = get_candidate_recipes(cur, profile)
        print(f"알레르기({profile['allergy']}) 제외 후 남은 후보: {len(candidates)}개\n")
        for c in candidates:
            print(f"  [{c['id']}] {c['menu_name']} | {c['category']} | {c['calorie']}kcal | {c['nutrition_group']}")

    conn.close()
