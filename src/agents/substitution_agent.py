"""
Substitution Agent [확장]
- 역할: 추천된 레시피에서 사용자가 갖고 있지 않은 재료(부족 재료)를 찾아,
        대체 가능한 재료를 제안하거나 생략 가능 여부를 안내한다.
- 참고: 완벽한 대체재 데이터베이스가 아니라, 자주 쓰는 재료 위주의 수동 매핑이다
        (지침 8번 원칙과 동일: 10~20개 정도만 다뤄도 충분).
- 최종 대체 가능 여부는 사용자가 직접 판단해야 하며, 이 제안은 참고용이다.
"""

from recommendation_agent import normalize_ingredient, ingredients_match
from tagging_agent import clean_ingredient_name

# 2026-07 개정(#80): 자주 쓰는 재료의 대체재 목록을 확장했다(완벽할 필요는 없음 - 지침 8번
# 원칙과 동일하게 자주 쓰는 것 위주). 기존에는 방향이 한쪽으로만 있는 항목(예: "양파"->"대파"는
# 있는데 "대파"->"양파"는 없음)이 있었는데, 실제로는 서로 바꿔 써도 되는 경우라 양방향으로
# 맞췄다. 새로 추가한 항목(고추장/쌈장, 식용유/올리브유, 참기름/들기름 등)은 실제로 자주
# "이거 없으면 저거 써도 돼"라고 조언되는 조합만 골랐다.
#
# 2026-07-19 추가(테스트/실사용 중 "대체재 정보 없음"이 자주 뜨는 재료를 보완): 채소류
# (파프리카/피망, 양배추/배추, 브로콜리/콜리플라워), 조미료(굴소스/진간장, 맛술/청주),
# 유제품(버터/마가린, 모짜렐라치즈/슬라이스치즈), 육가공(베이컨/스팸), 액젓(멸치액젓/
# 까나리액젓), 소고기 부위(우삼겹/차돌박이 - recommendation_agent.py의 BEEF_GROUP에는
# 이미 있지만 그건 추천 랭킹용이라 이 안내 목록과는 별개다)를 추가했다. 기준은 동일하게
# "실제로 요리할 때 흔히 조언되는 조합"만 골랐다.
SUBSTITUTES = {
    "두부": ["순두부", "연두부"],
    "순두부": ["두부", "연두부"],
    "연두부": ["두부", "순두부"],
    "돼지고기": ["소고기", "닭고기"],
    "소고기": ["돼지고기", "닭고기"],
    "닭고기": ["돼지고기", "소고기"],
    "새우": ["오징어", "조개류"],
    "오징어": ["새우", "조개류"],
    "조개류": ["새우", "오징어"],
    "양파": ["대파"],
    "대파": ["양파"],
    "표고버섯": ["양송이버섯", "느타리버섯"],
    "양송이버섯": ["표고버섯", "느타리버섯"],
    "느타리버섯": ["표고버섯", "양송이버섯"],
    "우유": ["두유"],
    "두유": ["우유"],
    "달걀": ["두부(식감 대체용)"],
    "고추장": ["쌈장"],
    "쌈장": ["고추장"],
    "식용유": ["올리브유", "카놀라유"],
    "올리브유": ["식용유", "카놀라유"],
    "참기름": ["들기름"],
    "들기름": ["참기름"],
    "설탕": ["올리고당", "물엿"],
    "올리고당": ["설탕", "물엿"],
    "물엿": ["설탕", "올리고당"],
    "밀가루": ["부침가루"],
    "부침가루": ["밀가루"],
    "애호박": ["주키니호박"],
    "주키니호박": ["애호박"],
    "콩나물": ["숙주나물"],
    "숙주나물": ["콩나물"],
    "미역": ["다시마"],
    "다시마": ["미역"],
    "청양고추": ["홍고추", "베트남고추"],
    "홍고추": ["청양고추"],
    "파프리카": ["피망"],
    "피망": ["파프리카"],
    "양배추": ["배추"],
    "배추": ["양배추"],
    "브로콜리": ["콜리플라워"],
    "콜리플라워": ["브로콜리"],
    "굴소스": ["진간장"],
    "맛술": ["청주"],
    "청주": ["맛술"],
    "버터": ["마가린"],
    "마가린": ["버터"],
    "모짜렐라치즈": ["슬라이스치즈"],
    "슬라이스치즈": ["모짜렐라치즈"],
    "베이컨": ["스팸"],
    "스팸": ["베이컨"],
    "멸치액젓": ["까나리액젓"],
    "까나리액젓": ["멸치액젓"],
    "우삼겹": ["차돌박이"],
    "차돌박이": ["우삼겹"],
}

# 없어도 맛에 큰 영향이 적어 생략 가능한 것으로 흔히 취급되는 재료(고명/향신용, 완벽하지 않음).
# 주의(#80): 이 목록은 "보통은" 고명/향신용이라는 뜻이지, 모든 레시피에서 항상 생략 가능하다는
# 뜻은 아니다 - 예를 들어 "시금치"는 대부분 나물무침의 고명이 아니라 "시금치나물"/"시금치된장국"
# 처럼 그 자체가 메뉴명에 들어간 핵심 재료인 경우도 있다. 그래서 get_missing_ingredients()에서는
# 이 목록에 있어도 "메뉴명에 그대로 박힌 재료"면 생략 가능 판정을 내리지 않도록 별도로 가려낸다
# (recommendation_agent.py의 core_ingredients 개념, #77과 같은 이유).
OMITTABLE = {"통깨", "실고추", "청고추", "시금치", "깨"}

# recipe_ingredients 테이블의 실제 수량(g)이 이 값 이하이면, OMITTABLE 목록에 없어도
# "고명급 소량 재료"로 보고 생략 가능하다고 판단한다(#80) - 하드코딩된 목록만 믿기보다,
# 실제 수량 데이터가 있으면 그걸 우선 쓰는 게 더 정확하기 때문이다. recommendation_agent.py의
# DEFAULT_UNIT_WEIGHT(10.0, g 단위 아닌 값의 기본치)보다 살짝 낮게 잡아서, "단위 정보가 없어서
# 기본값이 들어간 경우"까지 생략 가능으로 잘못 판단하지 않게 한다.
GARNISH_WEIGHT_THRESHOLD_G = 8.0


def _is_core_ingredient(ingredient_name: str, menu_name: str) -> bool:
    """
    이 재료명이 메뉴명에 그대로 들어있는지 확인한다(예: "시금치된장국"의 "시금치").
    recommendation_agent.py의 _find_core_ingredients()와 같은 기준(2글자 이상만 인정 -
    1글자는 우연히 겹칠 위험이 커서)을 쓴다. 메뉴명에 있다는 건 "이 요리는 이 재료 없이는
    성립하지 않는다"는 뜻이므로, 생략 가능 목록에 있어도 무시하고 대체재/구매 안내로 보낸다.
    """
    if not menu_name or len(ingredient_name) < 2:
        return False
    return ingredient_name in menu_name.replace(" ", "")


def _get_ingredient_gram_weight(cur, recipe_id: int, ingredient_name: str) -> float | None:
    """
    recipe_ingredients 테이블(실제 수량 정보가 있는 원본 데이터)에서 이 재료의 수량(g)을
    찾는다. g 단위가 아니거나 못 찾으면 None을 반환한다(모른다는 뜻 - 함부로 "소량"이라고
    추측하지 않는다).
    """
    cur.execute("SELECT name, amount, unit FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
    target = normalize_ingredient(ingredient_name)
    for raw_name, amount, unit in cur.fetchall():
        name = clean_ingredient_name(raw_name or "")
        if not name or unit != "g" or not isinstance(amount, (int, float)):
            continue
        if ingredients_match(normalize_ingredient(name), target):
            return float(amount)
    return None


def get_missing_ingredients(cur, recipe_id: int, user_ingredients: list[str], menu_name: str = "") -> list[dict]:
    """
    레시피의 재료 태그 중, 사용자가 갖고 있지 않은 것을 찾아 대체재 제안 또는 생략 가능
    여부와 함께 반환한다.

    주의(추천 원칙 3번 - 화면에 보여주는 재료/사용률은 무조건 정확하게): 예전에는 조미료
    (소금·식초·통깨 등, is_staple)를 여기서도 걸러냈는데, 그러면 사용자가 실제로 입력하지
    않은 식초·통깨 같은 재료가 "부족한 재료" 목록에 안 잡히고, 화면의 "재료" 목록에는
    그대로 나오는데 "부족한 재료"에는 안 나오는 모순이 생겼다. 그래서 화면 표시용인 이
    함수는 조미료도 그대로 포함해서 계산한다 (조미료를 매칭 대상에서 빼는 건 추천 순위를
    매기는 score_by_ingredients()에서만 하는 것으로 분리했다 - 그건 "표기"가 아니라
    "랭킹 알고리즘"이라 조미료 노이즈를 걸러내는 게 맞기 때문).

    2026-07 개정(#80) - 생략 가능 여부 판단 로직을 두 가지로 개선했다:
    1) menu_name을 받아서, OMITTABLE 목록에 있는 재료라도 그게 메뉴명에 그대로 들어있으면
       (예: "시금치된장국"의 "시금치") 생략 가능 판정을 내리지 않는다 - "고명"이 아니라
       "이 요리의 정체성"이기 때문이다(recommendation_agent.py의 core_ingredients와 같은 개념, #77).
    2) OMITTABLE 목록에 없는 재료라도, recipe_ingredients 테이블의 실제 수량이
       GARNISH_WEIGHT_THRESHOLD_G(8g) 이하면 "소량 재료"로 보고 생략 가능하다고 판단한다 -
       하드코딩된 목록 하나에만 의존하지 않고, 실제 데이터가 있으면 그걸 우선한다.
    대체재 제안도 개선했다: 유저가 이미 그 대체재 중 하나를 갖고 있으면 "이미 갖고 계신
    OO로 대체하세요"처럼 더 확실하게 안내하고, 하나도 없으면 기존처럼 후보만 나열한다.
    """
    cur.execute(
        "SELECT tag_value FROM recipe_tags WHERE recipe_id = ? AND tag_type = 'ingredient'",
        (recipe_id,)
    )
    recipe_ingredients = [row[0] for row in cur.fetchall()]

    user_norm = [normalize_ingredient(u.strip()) for u in user_ingredients if u.strip()]

    missing = []
    for ri in recipe_ingredients:
        ri_norm = normalize_ingredient(ri)
        # 단순 부분일치만 쓰면 "배추"가 "배"(과일)에 걸리는 것처럼 전혀 다른 재료가 우연히
        # 겹치는 문제가 있어서, ingredients_match()로 짧은 재료명 오매칭을 걸러낸다 (#71).
        has_it = any(ingredients_match(u, ri_norm) for u in user_norm)
        if has_it:
            continue

        # #77과 같은 개념: 메뉴명에 그대로 들어있는 재료는 "이 요리의 핵심"이므로 절대
        # 생략 가능으로 처리하지 않는다(OMITTABLE 목록에 있어도 무시).
        is_core = _is_core_ingredient(ri, menu_name)

        gram_weight = None if is_core else _get_ingredient_gram_weight(cur, recipe_id, ri)
        is_garnish_by_weight = gram_weight is not None and gram_weight <= GARNISH_WEIGHT_THRESHOLD_G

        if not is_core and (ri in OMITTABLE or is_garnish_by_weight):
            if is_garnish_by_weight and ri not in OMITTABLE:
                suggestion = f"생략 가능 (실제 사용량 {gram_weight:g}g, 소량이라 없어도 큰 지장 없음)"
            else:
                suggestion = "생략 가능 (고명/향 첨가용)"
            missing.append({"ingredient": ri, "suggestion": suggestion, "type": "omit"})
            continue

        if ri in SUBSTITUTES:
            candidates = SUBSTITUTES[ri]
            # 대체재 후보 중 유저가 이미 갖고 있는 게 있으면, 그걸 콕 집어서 안내한다
            # (#80) - "대체 가능: 순두부, 연두부"보다 "이미 갖고 계신 순두부로 대체하세요"가
            # 훨씬 실행하기 쉬운 안내이기 때문이다.
            owned_candidates = [
                c for c in candidates
                if any(ingredients_match(u, normalize_ingredient(c)) for u in user_norm)
            ]
            if owned_candidates:
                suggestion = f"이미 갖고 계신 {', '.join(owned_candidates)}(으)로 대체하세요"
            else:
                suggestion = f"대체 가능: {', '.join(candidates)} (다만 이것도 안 갖고 계실 수 있어요)"
            missing.append({"ingredient": ri, "suggestion": suggestion, "type": "substitute"})
        elif is_core:
            missing.append({
                "ingredient": ri,
                "suggestion": "이 요리의 핵심 재료라 생략·대체가 어려워요 (직접 구매 필요)",
                "type": "core_missing",
            })
        else:
            missing.append({"ingredient": ri, "suggestion": "대체재 정보 없음 (직접 구매 필요할 수 있음)", "type": "unknown"})

    return missing


def get_ingredient_coverage(cur, recipe_id: int, user_ingredients: list[str]) -> dict:
    """
    레시피 재료 중 사용자가 보유한 재료로 커버되는 비율을 계산한다 (#57, 목업의
    "보유 재료 사용률 92%" 배지용). get_missing_ingredients()와 완전히 같은 매칭 기준
    (조미료 포함, 전부 다 센다)을 쓰기 때문에, 화면에 같이 표시되는 "부족한 재료" 개수와
    이 함수의 missing 값이 서로 어긋나지 않는다 (추천 원칙 3번: 표시되는 수치는 정확해야 함).
    """
    cur.execute(
        "SELECT tag_value FROM recipe_tags WHERE recipe_id = ? AND tag_type = 'ingredient'",
        (recipe_id,)
    )
    recipe_ingredients = [row[0] for row in cur.fetchall()]
    total = len(recipe_ingredients)
    if total == 0:
        return {"total": 0, "matched": 0, "missing": 0, "coverage_pct": None}

    user_norm = [normalize_ingredient(u.strip()) for u in user_ingredients if u.strip()]
    matched = 0
    for ri in recipe_ingredients:
        ri_norm = normalize_ingredient(ri)
        if any(ingredients_match(u, ri_norm) for u in user_norm):
            matched += 1

    return {
        "total": total,
        "matched": matched,
        "missing": total - matched,
        "coverage_pct": round(matched / total * 100),
    }


if __name__ == "__main__":
    import sqlite3
    from recommendation_agent import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 테스트: 아까 그 "부추 콩가루 찜" 레시피(id=2로 가정)로 확인
    cur.execute("SELECT id, menu_name FROM recipes LIMIT 5")
    for recipe_id, menu_name in cur.fetchall():
        print(f"\n[{recipe_id}] {menu_name}")
        result = get_missing_ingredients(cur, recipe_id, ["계란", "안심", "밥"])
        for m in result:
            print(f"   - {m['ingredient']}: {m['suggestion']}")

    conn.close()
