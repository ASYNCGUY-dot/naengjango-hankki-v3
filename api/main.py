import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app = FastAPI(title="냉장고 한끼 API")

# CORS (2026-08-13, V3에서 추가)
#
# V2에는 이 설정이 없었고 그래도 동작했다. Reflex 프론트가 서버 쪽 Python에서 이 API를
# 불렀기 때문에 브라우저의 교차 출처 검사를 거치지 않았다. V3는 브라우저가 직접 부르는
# SPA라 이게 없으면 모든 요청이 preflight에서 막힌다(실제로 로그인에서 막혔다).
#
# 허용 주소는 환경변수로 넣는다. "*"로 열지 않는 이유는, 인증 토큰을 다루는 API라
# 아무 페이지나 사용자의 브라우저를 통해 호출하게 둘 이유가 없기 때문이다.
# Vite 기본 포트는 5173인데 다른 프로젝트가 쓰고 있으면 5174로 밀린다. 둘 다 허용해서
# 개발자가 포트를 신경 쓰지 않게 한다(로컬 주소라 열어도 위험이 없다).
_DEFAULT_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:5174,http://127.0.0.1:5174"
)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # 토큰을 Authorization 헤더로 보내고 쿠키를 쓰지 않으므로 자격증명 공유가 필요 없다.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

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
