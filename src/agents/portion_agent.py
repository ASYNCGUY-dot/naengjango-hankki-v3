"""
Portion Agent [확장] - 인원수 기반 분량 환산
- 역할: RCP_PARTS_DTLS에서 재료별 수량(숫자+단위)을 뽑아 recipe_ingredients 테이블에 저장하고,
        가구원 수(household_size)에 맞춰 수량을 환산해서 보여준다.
- 기준: 재료 텍스트 맨 앞에 "[N인분]" 표시가 있으면 그 값을 기준 인분으로, 없으면 1인분으로 가정한다.
- 참고: 분수 표기(3/4, 1½ 등)나 "약간"처럼 숫자가 없는 항목은 환산하지 않고 원문 그대로 보여준다
        (완벽한 파싱이 목표가 아님 - 지침 8번 원칙).
"""

import re
import json
import sqlite3

DB_PATH = "data/app.db"

PREP_PREFIXES = ["다진 ", "채썬 ", "슬라이스 ", "잘게 썬 ", "다지고 ", "으깬 "]
SKIP_WORDS = {"고명", "양념장", "양념", "소스", "밑간"}

QTY_PATTERN = re.compile(r"^(.*?)\s+([\d]+(?:\.\d+)?)\s*([가-힣a-zA-Z]*)")
SERVINGS_HEADER = re.compile(r"^\[(\d+)\s*인분\]")

# 공백 없이 "이름(숫자+단위)"로 붙어있는 경우 (예: "돼지고기(50g)", "애호박(1/2개)")
# 괄호 안이 숫자로 시작할 때만 수량으로 인정한다. "황태(채)"처럼 숫자가 아니면
# 재료 설명으로 보고 그대로 이름에 남겨둔다 (의도된 동작, 버그 아님).
NOSPACE_QTY_PATTERN = re.compile(r"^(.+?)\(([\d]+(?:/[\d]+)?(?:\.\d+)?)\s*([가-힣a-zA-Z]*)\)$")


def _parse_amount(amount_str: str) -> float:
    """'1/2', '1/4' 같은 분수 표기도 처리한다."""
    if "/" in amount_str:
        num, den = amount_str.split("/")
        return float(num) / float(den)
    return float(amount_str)


def parse_ingredients_with_amounts(parts_dtls: str) -> tuple[int, list[dict]]:
    """returns (base_servings, [{"name","amount","unit","raw_text"}, ...])"""
    header_match = SERVINGS_HEADER.match(parts_dtls.strip())
    base_servings = int(header_match.group(1)) if header_match else 1

    text = SERVINGS_HEADER.sub("", parts_dtls, count=1)
    tokens = re.split(r"[,\n]", text)

    items = []
    for token in tokens:
        token = token.strip().lstrip("·●・-")
        if not token:
            continue
        if ":" in token:
            token = token.split(":", 1)[1].strip()
        if not token or token in SKIP_WORDS:
            continue

        m = QTY_PATTERN.match(token)
        if m:
            name, amount_str, unit = m.group(1).strip(), m.group(2), m.group(3).strip()
            amount = _parse_amount(amount_str)
        else:
            m2 = NOSPACE_QTY_PATTERN.match(token)
            if m2:
                name, amount_str, unit = m2.group(1).strip(), m2.group(2), m2.group(3).strip()
                amount = _parse_amount(amount_str)
            else:
                name, amount, unit = token, None, None

        for prefix in PREP_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()

        if not name or name in SKIP_WORDS:
            continue

        items.append({"name": name, "amount": amount, "unit": unit, "raw_text": token})

    return base_servings, items


def get_recipe_ingredients(cur, recipe_id: int) -> tuple[int, list[dict]]:
    """DB에 저장해둔 recipe_ingredients에서 재료 수량 목록을 읽어온다."""
    cur.execute(
        "SELECT name, amount, unit, raw_text, base_servings FROM recipe_ingredients WHERE recipe_id = ?",
        (recipe_id,)
    )
    rows = cur.fetchall()
    if not rows:
        return 1, []

    base_servings = rows[0][4]
    items = [{"name": r[0], "amount": r[1], "unit": r[2], "raw_text": r[3]} for r in rows]
    return base_servings, items


def scale_ingredients(items: list[dict], base_servings: int, household_size: int) -> list[dict]:
    """
    household_size에 맞춰 수량을 환산한 텍스트를 만든다.
    amount/unit도 함께 반환한다 (Price Agent가 재료비를 계산할 때 필요하다).
    """
    factor = household_size / base_servings if base_servings else household_size
    scaled = []
    for item in items:
        if item["amount"] is None:
            display = item["raw_text"]  # 숫자를 못 뽑은 경우 원문 그대로
            scaled_amount = None
        else:
            scaled_amount = item["amount"] * factor
            # 소수점 한 자리까지만 (너무 정밀하게 보이지 않도록)
            scaled_amount = round(scaled_amount, 1)
            if scaled_amount == int(scaled_amount):
                scaled_amount = int(scaled_amount)
            display = f"{item['name']} {scaled_amount}{item['unit']}"
        scaled.append({
            "name": item["name"],
            "display": display,
            "amount": scaled_amount,
            "unit": item["unit"],
        })
    return scaled


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 파싱 규칙이 바뀔 수 있으니, 매번 지우고 다시 채운다 (건수가 많지 않아 재실행 비용이 적음).
    # 주의: 실행 전 Streamlit을 완전히 종료할 것 (동시 접근 시 DB 손상 위험).
    cur.execute("DELETE FROM recipe_ingredients")

    import os
    source_path = "data/api_samples/cookrcp01_all.json"
    if not os.path.exists(source_path):
        source_path = "data/api_samples/cookrcp01_50.json"
    if not os.path.exists(source_path):
        source_path = "data/api_samples/cookrcp01_sample.json"

    with open(source_path, "r", encoding="utf-8") as f:
        sample = json.load(f)
    recipes = sample["COOKRCP01"]["row"]

    # menu_name으로 찾으면 동명 레시피가 있을 때 엉뚱한 recipe_id에 매칭될 수 있다.
    # tagging_agent.py가 이 JSON을 같은 순서로 읽어 순서대로 저장했다는 점을 이용해,
    # id 오름차순으로 정렬한 recipes 목록과 JSON 목록을 순서대로 1:1 매칭한다.
    cur.execute("SELECT id FROM recipes ORDER BY id")
    recipe_ids = [row[0] for row in cur.fetchall()]

    if len(recipe_ids) != len(recipes):
        print(f"(경고) DB의 레시피 수({len(recipe_ids)})와 JSON 레시피 수({len(recipes)})가 다릅니다. "
              f"tagging_agent.py를 먼저 최신 데이터로 재실행했는지 확인하세요.")

    saved = 0
    for recipe_id, recipe in zip(recipe_ids, recipes):
        base_servings, items = parse_ingredients_with_amounts(recipe.get("RCP_PARTS_DTLS", ""))
        for item in items:
            cur.execute(
                "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, raw_text, base_servings) VALUES (?, ?, ?, ?, ?, ?)",
                (recipe_id, item["name"], item["amount"], item["unit"], item["raw_text"], base_servings)
            )
        saved += 1

    conn.commit()
    print(f"{saved}개 레시피의 재료 수량 다시 저장 완료 (기존 데이터 삭제 후 재생성)")

    conn.close()
