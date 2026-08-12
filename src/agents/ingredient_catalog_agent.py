"""
Ingredient Catalog Agent [확장] - 식품영양성분DB 전체를 로컬 DB로 벌크 수집 (#47)

왜 필요한가:
- ingredient_agent.match_nutrition()은 재료 이름 하나씩 실시간으로 공식 API를 호출하는 방식이라
  레시피 추천 흐름(재료 몇 개)에는 맞지만, "재료 찾아보기"처럼 전체 목록/검색을 보여주는 화면에는
  맞지 않는다.
- 이름 필터 없이 전체를 요청하면 총 302,629건이 나온다(2026-07 기준 실측). 한 번에 최대 500건씩
  받아도 약 606번의 API 호출이 필요해서, 화면을 열 때마다 실시간으로 부르는 건 불가능하고
  공공데이터포털 인증키의 하루 호출 한도도 금방 다 써버린다.
- 그래서 이 스크립트를 딱 한 번(또는 며칠에 걸쳐 나눠서) 실행해 전체 데이터를 ingredient_catalog
  테이블에 미리 저장해두고, 실제 서비스 화면(재료 찾아보기)은 이 로컬 테이블만 검색한다.

사용법 (터미널에서 직접 실행):
    python src/agents/ingredient_catalog_agent.py

- 실행할 때마다 이전에 어디까지 받았는지 data/ingredient_catalog_progress.json에 기록해두고
  이어서 받기 때문에, 중간에 멈추거나(할당량 초과 등) 여러 번에 나눠 실행해도 안전하다.
- 기본값은 한 번 실행에 최대 700페이지(전체 606페이지보다 넉넉함)까지 시도하므로, 보통 한 번
  실행으로 끝까지 받아진다. 만약 도중에 공공데이터포털 하루 호출 한도에 걸리면 자동으로 멈추고
  진행 상황이 저장되니, 그 다음엔 다음날 다시 실행하면 이어서 받는다.
"""

import os
import re
import json
import time
import sqlite3
import requests
from datetime import datetime
from dotenv import load_dotenv

from ingredient_agent import NUTRIENT_FIELDS, VITAMIN_MINERAL_FIELDS, INGREDIENT_ALIASES, GROUP_PRIORITY
from recommendation_agent import SYNONYM_MAP

load_dotenv()
API_KEY = os.getenv("NUTRITION_API_KEY")
DB_PATH = "data/app.db"
PROGRESS_FILE = "data/ingredient_catalog_progress.json"

API_URL = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
PAGE_SIZE = 500          # 이 API가 허용하는 한 번 요청당 최대 건수
# 전체가 약 606페이지라서, 이 값을 그보다 넉넉하게 잡아두면 한 번 실행으로 끝까지 시도한다.
# 실제 하루 호출 한도에 걸리면(공식 API가 에러를 주면) 자동으로 멈추고 진행 상황은 저장되므로,
# 다음날 다시 실행하면 이어서 받는다 - 그래서 이 값을 크게 잡아도 안전하다.
DEFAULT_MAX_PAGES_PER_RUN = 700
REQUEST_DELAY_SEC = 0.15  # 공공 API에 너무 빠르게 연속 요청하지 않도록 살짝만 쉬어준다


def _to_float(raw):
    """API 응답의 숫자 필드는 "1,670.000"처럼 콤마가 섞이거나 빈 문자열("")일 수 있다."""
    if raw in (None, ""):
        return None
    try:
        return float(str(raw).replace(",", ""))
    except ValueError:
        return None


# [빠른 개선] 상세 영양 가이드 조회를 실시간 API 대신 로컬 캐시로 우선 처리하기 위한 함수.
# 왜 필요한가: ingredient_agent.match_nutrition()은 재료 이름 하나마다 매번 공공데이터포털
# API를 실시간으로 호출한다(타임아웃 20초 + 재시도 1회). 그런데 이 파일(#47)이 이미 전체
# 302,629건을 로컬 ingredient_catalog 테이블에 통째로 받아뒀으므로, 대부분의 재료는 굳이
# 실시간으로 다시 물어볼 필요가 없다 - 이미 도서관 전체를 복사해뒀는데 책 한 권 찾을 때마다
# 다시 도서관에 전화하는 셈이었다. match_nutrition()과 완전히 같은 모양의 dict를 반환하고,
# 로컬에 없으면 None을 반환하니, 호출하는 쪽에서 그때만 match_nutrition()으로 폴백하면 된다.
_CATALOG_COLUMNS = [
    "food_code", "name", "db_group", "energy_kcal", "water_g", "protein_g", "fat_g",
    "ash_g", "carbs_g", "sugar_g", "fiber_g", "calcium_mg", "iron_mg", "potassium_mg",
    "sodium_mg", "vitamin_a_ug", "vitamin_b1_mg", "vitamin_b2_mg", "niacin_mg",
    "vitamin_c_mg", "vitamin_d_ug", "magnesium_mg", "zinc_mg",
]


def match_nutrition_local(cur, ingredient_name: str) -> dict | None:
    """
    match_nutrition()과 같은 모양의 결과를 로컬 ingredient_catalog 테이블에서만 찾아 반환한다.
    - 정확한 이름이 여러 db_group에 걸쳐 있으면 원재료성 > 가공식품 > 음식 우선순위로 고른다
      (match_nutrition()과 동일한 기준).
    - 정확히 일치하는 이름이 없으면 부분 일치(LIKE)로 근사치를 하나 찾아서 is_exact_match=False로
      표시한다.
    - 로컬에 아예 없으면 None을 반환한다 - 이 경우에만 호출하는 쪽에서 실시간 API로 폴백하면 된다.
    """
    search_name = INGREDIENT_ALIASES.get(ingredient_name, ingredient_name)
    cols_sql = ", ".join(_CATALOG_COLUMNS)

    cur.execute(f"SELECT {cols_sql} FROM ingredient_catalog WHERE name = ?", (search_name,))
    exact_rows = [dict(zip(_CATALOG_COLUMNS, row)) for row in cur.fetchall()]

    is_exact = True
    if exact_rows:
        exact_rows.sort(
            key=lambda r: GROUP_PRIORITY.index(r["db_group"])
            if r["db_group"] in GROUP_PRIORITY else len(GROUP_PRIORITY)
        )
        item = exact_rows[0]
    else:
        cur.execute(f"SELECT {cols_sql} FROM ingredient_catalog WHERE name LIKE ? LIMIT 1", (f"%{search_name}%",))
        row = cur.fetchone()
        if row is None:
            return None
        item = dict(zip(_CATALOG_COLUMNS, row))
        is_exact = False

    result = {
        "input_name": ingredient_name,
        "matched_food_name": item["name"],
        "food_code": item["food_code"],
        "db_group": item["db_group"],
        "is_exact_match": is_exact,
    }
    for key in _CATALOG_COLUMNS:
        if key not in ("food_code", "name", "db_group"):
            result[key] = item[key]
    return result


def load_progress() -> dict:
    if not os.path.exists(PROGRESS_FILE):
        return {"last_completed_page": 0, "total_count": None}
    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_progress(progress: dict):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def fetch_page(page_no: int) -> dict:
    """
    페이지 하나를 가져온다. 이름 필터(FOOD_NM_KR)를 주지 않아서 전체 데이터 중 이 페이지 몫이 온다.
    응답 형식: {"body": {"totalCount": 302629, "items": [...]}}
    """
    params = {
        "serviceKey": API_KEY,
        "pageNo": page_no,
        "numOfRows": PAGE_SIZE,
        "type": "json",
    }
    response = requests.get(API_URL, params=params, timeout=20)
    return response.json()


def parse_item(item: dict) -> dict:
    """API 응답 항목 하나를 ingredient_catalog 테이블 컬럼 이름에 맞춰 정리한다."""
    row = {
        "food_code": item.get("FOOD_CD"),
        "name": item.get("FOOD_NM_KR"),
        "db_group": item.get("DB_GRP_NM"),
    }
    for raw_key, friendly_key in NUTRIENT_FIELDS.items():
        row[friendly_key] = _to_float(item.get(raw_key))
    for raw_key, friendly_key in VITAMIN_MINERAL_FIELDS.items():
        row[friendly_key] = _to_float(item.get(raw_key))
    return row


def save_items(cur, items: list[dict]):
    now = datetime.now().isoformat()
    columns = [
        "food_code", "name", "db_group",
        *NUTRIENT_FIELDS.values(), *VITAMIN_MINERAL_FIELDS.values(),
        "updated_at",
    ]
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT OR REPLACE INTO ingredient_catalog ({', '.join(columns)}) VALUES ({placeholders})"

    for item in items:
        row = parse_item(item)
        if not row["food_code"] or not row["name"]:
            continue  # 식별자나 이름이 없는 이상한 항목은 건너뜀
        values = [row.get(col) for col in columns[:-1]] + [now]
        cur.execute(sql, values)


def run_bulk_collect(max_pages_per_run: int = DEFAULT_MAX_PAGES_PER_RUN):
    """
    이어받기 방식으로 전체 데이터를 수집한다. 한 번 호출에 max_pages_per_run 페이지까지만 진행하고,
    이미 다 받았으면 아무 것도 하지 않는다.
    """
    if not API_KEY:
        print("(오류) .env 파일에 NUTRITION_API_KEY가 없습니다.")
        return

    progress = load_progress()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    pages_done_this_run = 0
    try:
        while True:
            if progress["total_count"] is not None:
                total_pages = -(-progress["total_count"] // PAGE_SIZE)  # 올림 나눗셈
                if progress["last_completed_page"] >= total_pages:
                    print(f"이미 전체 {progress['total_count']}건을 다 받았습니다. 더 받을 게 없어요.")
                    break

            if pages_done_this_run >= max_pages_per_run:
                print(f"이번 실행 한도({max_pages_per_run}페이지)에 도달해서 멈춥니다.")
                print("더 받으려면 이 스크립트를 다시 실행하세요 (이어서 받습니다).")
                break

            next_page = progress["last_completed_page"] + 1
            data = fetch_page(next_page)

            body = data.get("body")
            if body is None:
                print(f"(경고) {next_page}페이지 응답에 body가 없습니다. 원문: {str(data)[:300]}")
                print("할당량 초과이거나 인증키 문제일 수 있습니다. 여기서 멈춥니다.")
                break

            if progress["total_count"] is None:
                progress["total_count"] = body.get("totalCount")
                print(f"전체 {progress['total_count']}건 확인. 페이지당 {PAGE_SIZE}건씩 받습니다.")

            items = body.get("items", [])
            if not items:
                print(f"{next_page}페이지에 더 이상 데이터가 없습니다. 수집을 종료합니다.")
                progress["last_completed_page"] = next_page
                break

            save_items(cur, items)
            conn.commit()

            progress["last_completed_page"] = next_page
            save_progress(progress)

            pages_done_this_run += 1
            received = min(next_page * PAGE_SIZE, progress["total_count"] or 0)
            print(f"{next_page}페이지 저장 완료 (누적 약 {received}/{progress['total_count']}건)")

            time.sleep(REQUEST_DELAY_SEC)

    except requests.exceptions.RequestException as e:
        print(f"(오류) 네트워크 문제로 중단되었습니다: {e}")
        print("지금까지 받은 내용은 저장되어 있으니, 나중에 다시 실행하면 이어서 받습니다.")
    finally:
        conn.close()


def get_ingredient_catalog_count(cur) -> int:
    cur.execute("SELECT COUNT(*) FROM ingredient_catalog")
    return cur.fetchone()[0]


# ingredient_agent.py의 GROUP_PRIORITY(원재료성 > 가공식품 > 음식)와 동일한 우선순위.
# "재료 찾아보기"에서 검색 결과가 많을 때, "(AOP)크로아상"처럼 제조사/상품코드가 붙은 가공식품보다
# 두부·계란 같은 순수 재료(원재료성)가 먼저 보이도록 정렬 기준으로 쓴다.
DB_GROUP_ORDER_SQL = "CASE db_group WHEN '원재료성' THEN 0 WHEN '가공식품' THEN 1 WHEN '음식' THEN 2 ELSE 3 END"


# 3번 설정(자주 쓰는 재료 우선)을 큐레이션 목록에 없는 나머지 모든 재료에도 적용한다
# (2026-07-21, 사용자 요청 - "3번 설정을 모든 재료에 적용해줘"). "팽이버섯" 같은 특정 이름을
# 큐레이션해둔 것과 별개로, 어떤 검색어든 "말린것/분말/데친것" 같은 가공 변형 접미사가 붙은
# 항목은 뒤로, 이름이 짧고 단순한(하위 품종 수식어가 안 붙은) 항목은 앞으로 오게 하는 원칙
# 자체를 전체 정렬 기준에 넣는다 - _pick_common_representative()의 _score()와 같은 원리다.
# LIKE 패턴을 SQL 문자열에 직접 박아넣지 않고 ?로 바인딩한다 - api/deps.py의
# SqliteStyleCursor가 "?"를 "%s"로 바꿔 psycopg2(Postgres)에 넘기는데, 문자열에 그대로 든
# "%말린%" 같은 리터럴 %가 있으면 psycopg2가 파라미터 자리로 잘못 해석해서
# "IndexError: tuple index out of range"가 난다(로컬 Postgres 연동 테스트에서 실제로 발견,
# sqlite3 직접 테스트/pytest에서는 %치환이 없어서 안 드러났었다).
VARIANT_PENALTY_SQL = (
    "CASE "
    "WHEN name LIKE ? OR name LIKE ? OR name LIKE ? THEN 2 "
    "WHEN name LIKE ? OR name LIKE ? OR name LIKE ? THEN 1 "
    "ELSE 0 END"
)
VARIANT_PENALTY_PARAMS = ("%말린%", "%분말%", "%엑기스%", "%데친%", "%구운%", "%삶은%")


# "재료 찾아보기" 검색 관련성 개선(2026-07-21, #req3): 실측해보니 "버섯"으로 검색하면
# 1,728건이 나오는데, 기존 정렬(원재료성 우선 + 이름 가나다순)은 "검은비늘버섯"·"꽃송이버섯"
# 처럼 낯선 품종이 자모 순서상 앞에 와서 "팽이버섯"·"표고버섯"처럼 실제로 자주 찾는 재료가
# 뒤로 밀렸다. 가나다순만으로는 관련성을 반영할 수 없어서, 실제 자취/가정 요리에서 자주 쓰는
# 재료 목록을 이 파일에서 직접 관리하고 검색 결과 맨 앞에 우선 노출한다(SEASONAL_INGREDIENTS,
# SYNONYM_MAP과 같은 방식의 수동 큐레이션).
COMMON_INGREDIENT_NAMES = [
    "팽이버섯", "새송이버섯", "느타리버섯", "표고버섯", "양송이버섯", "만가닥버섯", "목이버섯",
    "양파", "대파", "쪽파", "마늘", "생강", "감자", "고구마", "당근", "애호박", "호박", "무",
    "배추", "양배추", "오이", "토마토", "방울토마토", "콩나물", "숙주나물", "시금치",
    "청양고추", "풋고추", "고추", "피망", "파프리카", "브로콜리",
    "두부", "계란", "달걀", "우유", "치즈", "버터", "김치",
    "돼지고기", "소고기", "닭고기", "삼겹살",
    "고등어", "갈치", "명태", "동태", "오징어", "새우", "멸치", "김", "미역",
    "쌀", "현미",
]


def _pick_common_representative(cur, common: str, columns: list[str]) -> dict | None:
    """common(예: "팽이버섯")과 이름이 겹치는 원재료성 항목 중, 사용자가 실제로 떠올릴 법한
    "생것" 기본형을 대표로 하나 고른다. 말린것/분말/데친것 같은 가공 변형은 뒤로 미룬다."""
    col_sql = ", ".join(columns)
    cur.execute(
        f"SELECT {col_sql} FROM ingredient_catalog WHERE name LIKE ? AND db_group = '원재료성'",
        (f"%{common}%",),
    )
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    if not rows:
        return None

    def _score(item: dict) -> tuple:
        name = item["name"]
        if "말린" in name or "분말" in name or "엑기스" in name:
            variant_penalty = 2
        elif "데친" in name or "구운" in name or "삶은" in name:
            variant_penalty = 1
        else:
            variant_penalty = 0
        exact_bonus = 0 if name.startswith(f"{common}_생것") or name == common else 1
        return (variant_penalty, exact_bonus, len(name), name)

    rows.sort(key=_score)
    return rows[0]


def expand_search_terms(keyword: str) -> list[str]:
    """
    "계란"으로 검색해도 "달걀"로 등록된 순수 재료까지 함께 찾아지도록, recommendation_agent.py의
    동의어 사전(SYNONYM_MAP)을 양방향으로 적용해서 검색어를 넓힌다.
    예: "계란" 검색 -> ["계란", "달걀"] / "계란빵" 검색 -> ["계란빵", "달걀빵"]
    (동의어 사전은 한 곳(SYNONYM_MAP)에서만 관리하고 여기서는 그대로 재사용한다)
    """
    terms = [keyword]
    for raw, canonical in SYNONYM_MAP.items():
        if raw in keyword:
            terms.append(keyword.replace(raw, canonical))
        if canonical in keyword:
            terms.append(keyword.replace(canonical, raw))
    return list(dict.fromkeys(terms))  # 순서를 유지하면서 중복 제거


def search_ingredient_catalog(cur, keyword: str = "", limit: int = 20, offset: int = 0) -> list[dict]:
    """
    이름에 keyword(동의어 포함)가 포함된 재료를 검색한다 (재료 찾아보기 화면, #48).
    keyword가 비어있으면 전체를 페이지 단위로 보여준다.
    정렬은 순수 재료(원재료성) 우선 -> 가공 변형(말린것/분말/데친것 등) 아닌 것 우선 ->
    이름이 짧은 것 우선 -> 이름 순으로 한다. 뒤의 두 기준(변형 여부/길이)이 2026-07-21에
    추가된 부분으로, 큐레이션 목록(COMMON_INGREDIENT_NAMES)에 없는 재료도 똑같이 적용받는다.
    """
    columns = [
        "food_code", "name", "db_group",
        *NUTRIENT_FIELDS.values(), *VITAMIN_MINERAL_FIELDS.values(),
    ]
    col_sql = ", ".join(columns)
    order_sql = f"{DB_GROUP_ORDER_SQL}, {VARIANT_PENALTY_SQL}, LENGTH(name), name"

    if keyword.strip():
        stripped = keyword.strip()
        terms = expand_search_terms(stripped)
        where_sql = " OR ".join(["name LIKE ?"] * len(terms))
        params = [f"%{t}%" for t in terms]

        # 자주 쓰는 재료 우선 노출은 첫 페이지에서만 적용한다(2026-07-21, #req3) -
        # 뒤 페이지까지 매번 다시 계산할 필요는 없다.
        boosted: list[dict] = []
        exclude_codes: set = set()
        if offset == 0:
            for common in COMMON_INGREDIENT_NAMES:
                if stripped not in common and common not in stripped:
                    continue
                rep = _pick_common_representative(cur, common, columns)
                if rep and rep["food_code"] not in exclude_codes:
                    boosted.append(rep)
                    exclude_codes.add(rep["food_code"])

        cur.execute(
            f"SELECT {col_sql} FROM ingredient_catalog WHERE {where_sql} "
            f"ORDER BY {order_sql} LIMIT ? OFFSET ?",
            (*params, *VARIANT_PENALTY_PARAMS, limit, offset)
        )
        general_items = [dict(zip(columns, row)) for row in cur.fetchall()]
        combined = boosted + [item for item in general_items if item["food_code"] not in exclude_codes]
        return combined[:limit]
    else:
        cur.execute(
            f"SELECT {col_sql} FROM ingredient_catalog ORDER BY {order_sql} LIMIT ? OFFSET ?",
            (*VARIANT_PENALTY_PARAMS, limit, offset)
        )
    rows = cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def count_ingredient_catalog(cur, keyword: str = "") -> int:
    if keyword.strip():
        terms = expand_search_terms(keyword.strip())
        where_sql = " OR ".join(["name LIKE ?"] * len(terms))
        params = [f"%{t}%" for t in terms]
        cur.execute(
            f"SELECT COUNT(*) FROM ingredient_catalog WHERE {where_sql}",
            params
        )
    else:
        cur.execute("SELECT COUNT(*) FROM ingredient_catalog")
    return cur.fetchone()[0]


if __name__ == "__main__":
    import sys

    # 터미널에서 원하는 개수로 실행하고 싶으면: python src/agents/ingredient_catalog_agent.py 50
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAX_PAGES_PER_RUN
    run_bulk_collect(max_pages_per_run=max_pages)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    print(f"\n현재 ingredient_catalog에 저장된 재료 수: {get_ingredient_catalog_count(cur)}건")
    conn.close()
