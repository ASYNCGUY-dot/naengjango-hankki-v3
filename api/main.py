import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# .env를 파일 위치 기준으로 먼저 읽는다 (2026-08-13).
#
# 다른 모듈들은 load_dotenv()를 인자 없이 부르는데, 그건 실행 디렉터리에서 .env를 찾는다.
# uvicorn을 저장소 밖에서 띄우면(--app-dir로 지정하는 경우) 못 찾고, POSTGRES_URL이 비어
# psycopg2가 기본값인 localhost:5432에 붙으려다 실패한다. 실제로 겪었고, 증상이
# "연결 거부"라 원인이 .env라는 걸 알아채기 어려웠다.
#
# 여기서 먼저 채워두면 이후 모듈의 load_dotenv()는 덮어쓰지 않으므로(기본 동작) 그대로 둬도 된다.
# 이 import는 api.routers보다 위에 있어야 한다 - deps.py가 import 시점에 값을 읽는다.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from api.routers import (  # noqa: E402
    admin,
    auth,
    brag,
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

# 처리되지 않은 예외를 여기서 잡는다 (2026-08-13).
#
# 안 잡으면 Starlette의 기본 처리기가 CORS 미들웨어 바깥에서 응답을 만들어, 500 응답에
# CORS 헤더가 붙지 않는다. 그러면 브라우저는 이걸 "CORS 차단"으로 보고하고 화면에는
# "연결에 실패했습니다"만 뜬다. 실제로 겪었다 - 원인은 DB 컬럼 누락이었는데 프론트에서는
# CORS 문제로 보여서 한참 엉뚱한 곳을 봤다.
#
# 이 데코레이터가 CORSMiddleware 추가보다 먼저 와야 한다. Starlette은 나중에 추가한
# 미들웨어를 바깥에 두므로, 이 순서라야 CORS가 바깥에서 헤더를 붙일 수 있다.
@app.middleware("http")
async def catch_unhandled_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        # 서버 로그에는 원인을 그대로 남긴다. 응답에는 담지 않는다 - 내부 구조가
        # 사용자에게 새어나갈 이유가 없다.
        logging.getLogger("api").exception("처리되지 않은 오류: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "서버에서 문제가 발생했습니다. 잠시 후 다시 시도해주세요."},
        )


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
app.include_router(brag.router)


@app.get("/health")
def health():
    return {"status": "ok"}
