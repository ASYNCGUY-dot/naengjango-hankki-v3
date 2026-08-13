from fastapi import FastAPI

from api.routers import (
    admin,
    auth,
    favorite,
    ingredient_catalog,
    ingredient_submission,
    like,
    nutrition,
    pantry,
    popular_videos,
    price,
    profile,
    recommendation,
    review,
    safety,
    seasonal,
    shopping,
    substitution,
    user_recipe,
)

app = FastAPI(title="냉장고 한끼 V2 API")

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(pantry.router)
app.include_router(safety.router)
# like.router가 recommendation.router보다 먼저 와야 한다: 둘 다 "/recommendation/recipes/..."
# 아래에 라우트가 있는데, recommendation.router의 "/recipes/{recipe_id}"(recipe_id: int)가
# like.router의 리터럴 경로 "/recipes/popular"보다 먼저 등록되면 "popular"이 그 경로 패턴에
# 먼저 매칭되어(문자열로는 매칭되고 이후 int 변환에서 422) like.router까지 못 간다
# (2026-07-21, #req5 - 인기 레시피 엔드포인트 추가하며 발견).
app.include_router(like.router)
app.include_router(recommendation.router)
app.include_router(favorite.router)
app.include_router(review.router)
app.include_router(substitution.router)
app.include_router(popular_videos.router)
app.include_router(ingredient_catalog.router)
app.include_router(user_recipe.router)
app.include_router(price.router)
app.include_router(nutrition.router)
app.include_router(seasonal.router)
app.include_router(shopping.router)
# like.router는 위(recommendation.router 앞)에서 이미 등록했다. 여기에도 있던 중복 등록을
# V3에서 제거했다 - 순서 문제를 고치며 앞쪽에 추가하고 원래 줄을 안 지운 흔적이었다.
# 기능상 첫 등록이 이겨서 동작은 했지만, OpenAPI 명세에 같은 오퍼레이션이 두 번 실려
# 생성 타입의 이름이 어그러졌다(로컬에서 명세를 뽑으며 경고로 드러났다).
app.include_router(ingredient_submission.router)


@app.get("/health")
def health():
    return {"status": "ok"}
