"""
V1의 recommendation_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
get_user_profile -> get_candidate_recipes -> score_by_ingredients 순서는 그대로 유지한다.

목업 대비 디자인 재검토(2026-07-18)에서 추천 카드에 4대 영양소(칼로리/단백질/지방/탄수화물)
요약을 보여주기로 해서, get_candidate_recipes가 이미 SELECT해오는 nutrients_json을
(agent 함수는 건드리지 않고) 이 라우터 계층에서만 파싱해 개별 필드로 노출한다.

2026-07-19 추가: 추천 화면 개편 - 지금까지는 이 엔드포인트가 항상 DB의 보유 재료(pantry)를
그대로 읽어서 계산했는데, "이번 추천에만 쓸 재료를 그때그때 직접 구성하고 싶다"는 요청으로
호출부(프론트)가 넘긴 ingredients 목록을 그대로 쓰도록 바꿨다. pantry 자동 조회는 제거했다 -
"냉장고에서 불러오기"는 이제 프론트가 pantry_items를 읽어 이 목록에 채워 넣는 방식으로
바뀌었으므로, 서버가 이중으로 pantry를 조회할 필요가 없다.
"""

import json
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from pydantic import BaseModel

from api import usage_log
from api.auth_token import get_current_user_id, get_optional_user_id, require_self
from api.deps import get_db
from src.agents import portion_agent, recommendation_agent, seasonal_agent

router = APIRouter(prefix="/recommendation", tags=["recommendation"])


def _parse_nutrients(nutrients_json: str | None) -> dict:
    if not nutrients_json:
        return {}
    try:
        raw = json.loads(nutrients_json)
    except (ValueError, TypeError):
        return {}
    parsed = {}
    for key in ("energy_kcal", "protein_g", "fat_g", "carbs_g"):
        value = raw.get(key)
        try:
            parsed[key] = float(value) if value is not None else None
        except (ValueError, TypeError):
            parsed[key] = None
    return parsed


class RecommendationItem(BaseModel):
    id: int
    menu_name: str
    category: str | None
    calorie: float | None
    nutrition_group: str
    image_url: str | None
    youtube_url: str | None
    ingredient_overlap: int
    coverage_ratio: float
    qualifies: bool
    has_protein_match: bool
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None


class RecipeIngredient(BaseModel):
    name: str
    amount: float | None
    unit: str | None
    # 이 행이 재료인지 구획 제목인지를 서버가 정해서 내려준다.
    #
    # 예전에는 화면이 "수량이 없으면 구획 제목"으로 판단했는데 틀렸다. 수량 없는 행
    # 649개 중 진짜 제목은 4개뿐이고 나머지는 "소금적당량"처럼 수량이 글자로 적힌 진짜
    # 재료였다. 그래서 309개 레시피(27%)에서 재료가 제목으로 잘못 그려지거나, 목록 끝에
    # 있으면 화면에서 아예 사라졌다. 판정 규칙을 화면에 두면 또 어긋난다.
    kind: str  # "ingredient" | "section"


class RecipeDetail(BaseModel):
    id: int
    menu_name: str
    cook_method: str | None
    category: str | None
    calorie: float | None
    nutrition_group: str
    nutrients_json: str | None
    steps_json: str | None
    youtube_url: str | None
    image_url: str | None
    # 인가 없이도 재료를 볼 수 있어야 한다(2026-08-13). get_recipe() 주석 참고.
    ingredients: list[RecipeIngredient] = []
    base_servings: int | None = None


# "/demo"는 "/{user_id}"(user_id: int)보다 먼저 등록해야 한다 - 뒤에 두면 "demo"가
# user_id 자리에 매칭 시도되다 int 변환에 실패해 422가 난다(#req5의 popular과 같은 문제).
@router.get("/demo", response_model=list[RecommendationItem])
def recommend_demo(
    ingredients: list[str] = Query(default=[]),
    allergy: str = "",
    cur: sqlite3.Cursor = Depends(get_db),
):
    """로그인 없이 추천 로직만 체험하는 데모용 엔드포인트(2026-08-10).

    실제 서비스는 회원가입과 5단계 온보딩을 거쳐야 추천 화면에 닿는다. 포트폴리오
    링크를 받은 사람이 그 과정 없이 핵심 기능을 바로 볼 수 있도록 인가 없이 열어둔다.
    프로필은 DB에서 읽지 않고 쿼리로 받은 알레르기만으로 즉석에서 만든다 - 원본
    로직이 프로필에서 실제로 참조하는 값이 알레르기 하나뿐이라 가능하다.

    공개 엔드포인트이므로 개인 데이터(pantry/즐겨찾기 등)는 일절 건드리지 않고,
    남용 시 서버 부하가 커지지 않도록 재료 개수와 결과 개수를 상한으로 묶는다.
    """
    user_ingredients = [name.strip() for name in ingredients if name.strip()][:20]
    profile = {"allergy": (allergy or "").strip()}

    candidates = recommendation_agent.get_candidate_recipes(cur, profile)
    scored = recommendation_agent.score_by_ingredients(cur, candidates, user_ingredients)

    top = scored[:5]
    for item in top:
        item.update(_parse_nutrients(item.get("nutrients_json")))
    return top


@router.get("/{user_id}", response_model=list[RecommendationItem])
def recommend(
    user_id: int,
    limit: int = 10,
    ingredients: list[str] = Query(default=[]),
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    profile = recommendation_agent.get_user_profile(cur, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")

    user_ingredients = [name.strip() for name in ingredients if name.strip()]

    candidates = recommendation_agent.get_candidate_recipes(cur, profile)
    scored = recommendation_agent.score_by_ingredients(cur, candidates, user_ingredients)

    top = scored[:limit]
    for item in top:
        item.update(_parse_nutrients(item.get("nutrients_json")))
    usage_log.record(cur, usage_log.RECOMMEND, user_id=user_id)
    return top


@router.get("/{user_id}/alternative/{recipe_id}", response_model=RecommendationItem)
def get_alternative(
    user_id: int,
    recipe_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """"이 메뉴가 싫다면?" 버튼(2026-07-21, #req6) - recipe_id의 영양군과 같으면서
    칼로리가 가장 비슷한 다른 레시피를 재료와 무관하게 하나 골라준다."""
    require_self(user_id, current_user_id)
    profile = recommendation_agent.get_user_profile(cur, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")

    current = recommendation_agent.get_recipe_by_id(cur, recipe_id)
    if current is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")

    alternative = recommendation_agent.get_alternative_recipe(
        cur, profile, recipe_id, current["nutrition_group"]
    )
    if alternative is None:
        raise HTTPException(status_code=404, detail="대체할 만한 레시피를 찾지 못했습니다.")

    alternative.update(_parse_nutrients(alternative.get("nutrients_json")))
    # RecommendationItem이 요구하는 필드(ingredient_overlap 등)는 재료 무관 추천이라 의미가
    # 없으니 0/False 기본값으로 채운다 - 프론트는 이 응답을 별도의 간단한 카드로 보여준다.
    alternative.setdefault("ingredient_overlap", 0)
    alternative.setdefault("coverage_ratio", 0.0)
    alternative.setdefault("qualifies", False)
    alternative.setdefault("has_protein_match", False)
    return alternative


class RecipeSummary(BaseModel):
    id: int
    menu_name: str
    category: str | None
    calorie: float | None
    # 목록 카드가 사진 중심이라 여기서 함께 준다(2026-08-13). 없으면 화면이 레시피마다
    # 상세를 한 번씩 더 불러야 한다. 원본이 http라 표시할 때 https로 바꿔 쓴다.
    image_url: str | None


class CategoryCount(BaseModel):
    category: str
    count: int


class RecipeTheme(BaseModel):
    """홈 화면의 테마 한 줄."""

    key: str
    title: str
    subtitle: str | None = None
    # 열 개만 보여주고 끝이면 그게 전부인지 일부인지 알 수 없다. 규모를 함께 준다.
    total: int
    recipes: list[RecipeSummary]


# "/recipes/categories"와 "/recipes/search"는 "/recipes/{recipe_id}"보다 먼저 등록해야 한다 -
# 안 그러면 "categories"가 recipe_id 자리에 매칭 시도되다 int 변환에 실패해 422가 난다
# (#req5에서 popular 엔드포인트로 겪은 것과 같은 문제, api/main.py 참고).
@router.get("/recipes/categories", response_model=list[CategoryCount])
def list_categories(cur: sqlite3.Cursor = Depends(get_db)):
    """분류 필터 칩에 쓸 목록. 이름을 화면에 하드코딩하지 않으려고 실제 데이터에서 뽑는다.
    개수를 함께 주는 이유는, 결과가 적은 분류를 화면이 미리 알 수 있어서다."""
    return recommendation_agent.get_recipe_categories_with_counts(cur)


@router.get("/recipes/themes", response_model=list[RecipeTheme])
def list_home_themes(
    limit: int = Query(default=10, ge=1, le=20),
    month: int | None = Query(default=None, ge=1, le=12),
    cur: sqlite3.Cursor = Depends(get_db),
):
    """홈 화면에 줄 단위로 보여줄 테마들.

    홈이 가나다순 20개를 한 덩어리로 쏟아내 "어지럽다"는 피드백을 받아 만들었다
    (2026-08-18). 테마는 데이터가 지탱하는 것만 쓴다 - 요청에 있던 한식·중식·일식과
    난이도는 recipes에 컬럼이 없어 만들 수 없고, 난이도는 재료 개수로 대신한다.

    month는 테스트와 미리보기용이다. 안 주면 오늘 날짜를 쓴다.
    """
    resolved_month = month or date.today().month
    return recommendation_agent.get_home_themes(
        cur,
        seasonal_agent.get_current_season_ingredients(resolved_month),
        resolved_month,
        limit,
    )


@router.get("/recipes/search", response_model=list[RecipeSummary])
def search_recipes(
    keyword: str = "",
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
    cur: sqlite3.Cursor = Depends(get_db),
):
    """레시피 목록 조회. 프로필/알레르기 필터 없는 공개 조회라 인가를 요구하지 않는다.

    category와 offset은 에이전트가 이미 지원하던 것을 여기서 열어준 것이다(2026-08-13).
    홈 화면의 분류 칩과 "더 보기"가 이걸 쓴다. 응답이 limit보다 적게 오면 마지막 쪽이다.
    """
    return recommendation_agent.search_all_recipes(
        cur, keyword=keyword, limit=limit, offset=offset, category=category
    )


@router.get("/recipes/{recipe_id}", response_model=RecipeDetail)
def get_recipe(
    recipe_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    viewer_id: int | None = Depends(get_optional_user_id),
):
    recipe = recommendation_agent.get_recipe_by_id(cur, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")

    # 재료 목록을 함께 준다(2026-08-13). 지금까지 재료를 주는 엔드포인트는 인가가
    # 필요했는데(가구원 수에 맞춰 환산하느라 프로필을 읽는다), 그러면 레시피 링크를
    # 공유받은 사람이 재료를 못 본다. 재료 없는 레시피는 레시피가 아니고, 링크 공유가
    # 되는 것이 React 전환의 핵심 이득이었다.
    #
    # 여기서는 환산하지 않은 원본 수량만 준다. 가구원 수 환산은 개인화라
    # /recipes/{id}/ingredients(인가 필요)에 그대로 남는다.
    base_servings, items = portion_agent.get_recipe_ingredients(cur, recipe_id)
    recipe["base_servings"] = base_servings
    # 안내 문구가 재료 행으로 들어온 것("1인분 기준<br>" 등)은 아예 빼고 보낸다.
    # 화면이 걸러내게 하면 다른 화면에서 또 새어나온다.
    classified = [
        (portion_agent.classify_ingredient_row(item["name"], item["amount"]), item)
        for item in items
    ]
    recipe["ingredients"] = [
        {"name": item["name"], "amount": item["amount"], "unit": item["unit"], "kind": kind}
        for kind, item in classified
        if kind != "noise"
    ]
    usage_log.record(cur, usage_log.RECIPE_VIEW, user_id=viewer_id, recipe_id=recipe_id)
    return recipe
