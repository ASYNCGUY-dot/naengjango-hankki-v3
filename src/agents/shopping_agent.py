"""
Shopping Agent - 부족한 재료 구매 링크 (#79, #95)

재료명으로 네이버쇼핑·쿠팡 검색 결과 페이지 링크를 만든다. 상품·가격·재고를 보장하지
않는다 - 사용자가 검색 결과를 보고 직접 고른다.

쿠팡은 제휴(수수료) 링크가 될 수 있다. Deeplink API로 원본 검색 URL을 트래킹 링크로
바꾸는데, 그러려면 쿠팡파트너스 **최종승인**이 있어야 한다(누적 판매가 일정 금액을
넘어야 열린다, 2026-09-11 확인). 승인 전에는 호출이 실패하고 원본 URL이 그대로 쓰인다.

네이버는 제휴가 안 된다. 네이버 쇼핑 커넥트가 생겼지만 크리에이터가 **특정 스마트스토어
상품을 골라 상품별 링크를 발급**받는 구조라, 재료명으로 검색 URL을 만드는 이 방식에는
붙일 수 없다(2026-09-11 확인). 사용자에게는 여전히 쓸모가 있어 버튼은 남긴다.

누구 키를 쓰는지는 get_shopping_key_for_recipe()가 정한다. 공식 레시피와 아직 기준에
못 미친 유저 레시피는 사이트 키, 기준을 넘긴 유저 레시피는 작성자 키다.
"""

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv

import requests

# 다른 agent들(ingredient_agent.py 등)과 같은 방식: .env 파일에 적어둔 값을 os.environ으로
# 불러온다. .env는 프로젝트 최상위 폴더(app.py와 같은 위치)에 있는 파일이다.
load_dotenv()

# 사이트 기본 키(지수님 본인 계정) - 공식 레시피 및 아직 크리에이터 본인 키를 등록 안 한
# 유저 레시피의 구매 링크에는 전부 이 키가 쓰인다.
COUPANG_ACCESS_KEY = os.getenv("COUPANG_ACCESS_KEY")
COUPANG_SECRET_KEY = os.getenv("COUPANG_SECRET_KEY")

# [#95] 유저 레시피의 추천이 이 개수 이상 쌓이면, 그 레시피의 재료 구매 링크에 사이트 기본 키
# 대신 작성자 본인의 쿠팡파트너스 키를 써서 수수료가 작성자에게 간다.
#
# 노출 승격 기준(USER_RECIPE_MIN_LIKES=3)과 **다른 값**이다. 여기서 새로 정의하지 않고
# recommendation_agent에서 가져다 쓴다 - 두 곳에 적으면 반드시 어긋난다.
from recommendation_agent import USER_RECIPE_REVENUE_MIN_LIKES  # noqa: E402


_logger = logging.getLogger("shopping_agent")

# 쿠팡 Open API 게이트웨이. 서명 방식(CEA)은 공식 문서로 확인했다 (2026-09-11):
#   message = datetime + method + path + query,  datetime은 yyMMddTHHmmssZ,
#   HmacSHA256 hexdigest,  헤더는
#   "CEA algorithm=HmacSHA256, access-key=..., signed-date=..., signature=..."
# 다만 **파트너스(affiliate) 쪽 문서는 로그인 뒤에 있어 경로와 응답 형태를 공식으로
# 확인하지 못했다.** 아래 경로와 필드명은 커뮤니티 SDK를 근거로 한 것이라 실제 승인 뒤
# 첫 호출에서 맞는지 확인해야 한다. 그때까지 이 코드는 실행되지 않는다 - 키가 없으면
# 아래에서 곧바로 원본 URL을 돌려주기 때문이다.
COUPANG_API_HOST = "https://api-gateway.coupang.com"
COUPANG_DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
COUPANG_TIMEOUT_SECONDS = 5


def _coupang_authorization(method: str, path: str, query: str, access_key: str, secret_key: str) -> str:
    """CEA 인증 헤더를 만든다. 서명 대상은 datetime + method + path + query 순서다."""
    # 포맷의 Z는 UTC를 뜻한다. localtime으로 만들면 시간대가 어긋나 서명이 거절되므로
    # gmtime을 쓴다(쿠팡 공식 예제는 strftime 기본값을 써서 이 부분이 로컬시간이다).
    signed_date = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = signed_date + method + path + query
    signature = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return (
        f"CEA algorithm=HmacSHA256, access-key={access_key}, "
        f"signed-date={signed_date}, signature={signature}"
    )


# 변환이 실패한 뒤 다시 시도하기까지 쉬는 시간.
#
# 승인 전 키로는 호출이 **항상** 실패한다. 쉬는 시간이 없으면 레시피 상세를 열 때마다
# 5초짜리 실패를 반복하고, 무료 티어(0.1 CPU)에서 그 시간은 그대로 사용자 대기가 된다.
# 실패를 기억했다가 한동안 건너뛴다. 승인이 나면 10분 안에 저절로 다시 붙는다.
COUPANG_FAILURE_COOLDOWN_SECONDS = 600
# 키를 그대로 담지 않는다. 유저 자격증명을 프로세스 메모리에 오래 들고 있을 이유가 없고,
# 여기 필요한 건 "같은 키인가"뿐이라 해시로 충분하다.
_last_failure_at: dict[str, float] = {}


def _cooldown_key(access_key: str) -> str:
    return hashlib.sha256(access_key.encode("utf-8")).hexdigest()


def _in_cooldown(access_key: str) -> bool:
    failed_at = _last_failure_at.get(_cooldown_key(access_key))
    return failed_at is not None and (time.monotonic() - failed_at) < COUPANG_FAILURE_COOLDOWN_SECONDS


def convert_to_coupang_partner_links(
    urls: list[str], access_key: str | None = None, secret_key: str | None = None
) -> dict[str, str]:
    """원본 쿠팡 URL들을 수수료가 잡히는 트래킹 링크로 바꾼다 (#95).

    **한 번에 다 보낸다.** Deeplink API가 `coupangUrls` 배열을 받으므로 재료 하나당
    요청 하나를 보낼 이유가 없다. 부족한 재료가 일곱 개면 요청도 일곱 번이었고, 승인
    전이라 전부 실패하면 타임아웃 5초 × 7 = 35초가 화면 대기로 그대로 얹혔다.

    **실패하면 원본 URL을 그대로 쓴다.** 이 함수는 화면을 그리는 경로 한가운데 있어서,
    여기서 예외가 나면 부족한 재료 목록 자체가 안 보인다. 수수료가 안 잡히는 것보다
    재료를 못 보는 쪽이 나쁘다. 유저가 키를 등록해도 쿠팡 최종승인(누적 판매 15만원)
    전에는 API가 안 열리므로, 이 실패는 예외가 아니라 정상 상태다.
    """
    access_key = access_key or COUPANG_ACCESS_KEY
    secret_key = secret_key or COUPANG_SECRET_KEY
    unchanged = {url: url for url in urls}
    if not access_key or not secret_key or not urls:
        return unchanged
    if _in_cooldown(access_key):
        return unchanged

    try:
        # POST라 쿼리 문자열이 없다. 서명 대상에서도 빈 문자열이다.
        authorization = _coupang_authorization(
            "POST", COUPANG_DEEPLINK_PATH, "", access_key, secret_key
        )
        response = requests.post(
            COUPANG_API_HOST + COUPANG_DEEPLINK_PATH,
            json={"coupangUrls": urls},
            headers={"Authorization": authorization, "Content-Type": "application/json"},
            timeout=COUPANG_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        converted = dict(unchanged)
        for row in response.json().get("data") or []:
            original = row.get("originalUrl")
            landing = row.get("shortenUrl") or row.get("landingUrl")
            # 응답이 보낸 순서대로 온다고 가정하지 않는다. originalUrl로 맞춘다.
            if original in converted and landing:
                converted[original] = landing
        _last_failure_at.pop(_cooldown_key(access_key), None)
        return converted
    except Exception:  # noqa: BLE001
        # 키가 아직 안 열린 상태가 흔하므로 warning으로만 남기고 조용히 원본을 쓴다.
        _last_failure_at[_cooldown_key(access_key)] = time.monotonic()
        _logger.warning("쿠팡 딥링크 변환 실패, 원본 URL을 그대로 쓴다", exc_info=True)
        return unchanged


def convert_to_coupang_partner_link(url: str, access_key: str | None = None, secret_key: str | None = None) -> str:
    """URL 하나짜리 편의 함수. 여러 개면 convert_to_coupang_partner_links를 쓸 것."""
    return convert_to_coupang_partner_links([url], access_key, secret_key)[url]


def naver_shopping_url(ingredient_name: str) -> str:
    """네이버쇼핑 검색 결과 페이지 링크를 만든다. (아직 제휴 링크 아님 - 위 설명 참고)"""
    query = quote(ingredient_name.strip())
    return f"https://search.shopping.naver.com/search/all?query={query}"


def coupang_search_url(ingredient_name: str, key_info: dict | None = None) -> str:
    """쿠팡 검색 결과 페이지 링크를 만든다. 제휴 키가 있으면 트래킹 링크로 바꾼다.

    재료가 여러 개면 이걸 반복해서 부르지 말고 get_shopping_links_for()를 쓸 것 -
    그쪽은 변환 요청을 한 번으로 묶는다.
    """
    url = coupang_raw_search_url(ingredient_name)

    if key_info is None:
        return convert_to_coupang_partner_link(url)

    # earner가 "none"이면 **아무 키도 쓰지 않는다.** 여기서 사이트 키로 되돌리면
    # 작성자 레시피에서 나온 구매를 사이트가 가져가게 되어 이 기능의 취지와 반대가 된다.
    if key_info.get("earner") == "none":
        return url

    return convert_to_coupang_partner_link(
        url, key_info.get("access_key"), key_info.get("secret_key")
    )


def get_shopping_links(ingredient_name: str, key_info: dict | None = None) -> dict:
    """재료 하나의 쇼핑 링크. 여러 개면 get_shopping_links_for()를 쓸 것.

    네이버는 제휴가 아니라 그냥 검색 링크다. 네이버 쇼핑 커넥트는 크리에이터가 특정
    스마트스토어 상품을 골라 상품별 링크를 발급받는 구조라, 재료명으로 검색 URL을 만드는
    지금 방식에 수수료를 붙일 수 없다(2026-09-11 확인). 사용자에게는 여전히 쓸모가 있어
    버튼은 남긴다.
    """
    return {
        "naver": naver_shopping_url(ingredient_name),
        "coupang": coupang_search_url(ingredient_name, key_info),
    }


def get_shopping_links_for(ingredient_names: list[str], key_info: dict | None = None) -> dict:
    """재료 여럿의 쇼핑 링크를 한 번에 만든다.

    돌려주는 것:
        {"links": [{"ingredient", "naver", "coupang"}, ...], "earner": str}

    두 가지를 여기서 처리한다.

    **변환 요청을 하나로 묶는다.** 재료마다 부르면 부족한 재료가 일곱 개일 때 요청도
    일곱 번이고, 승인 전이라 전부 실패하면 타임아웃이 그만큼 쌓여 화면 대기가 된다.

    **`earner`를 실제 결과로 정한다.** key_info의 earner는 "누구 키를 쓸 작정인가"이지
    "실제로 제휴 링크가 붙었는가"가 아니다. 그 둘을 같게 두면 화면이 "훠궈맨님에게
    수수료가 갑니다"라고 적어놓고 정작 링크는 평범한 검색 URL인 상태가 된다 - 아무도
    못 받는 돈을 특정인이 받는다고 말하는 셈이다. 변환이 한 건도 안 붙었으면 "none"으로
    낮춰서, 화면이 고지를 아예 안 달게 한다.
    """
    intended = (key_info or {}).get("earner", "site")
    urls = {name: coupang_raw_search_url(name) for name in ingredient_names}

    if intended == "none" or not urls:
        converted = {url: url for url in urls.values()}
    else:
        converted = convert_to_coupang_partner_links(
            list(urls.values()),
            (key_info or {}).get("access_key"),
            (key_info or {}).get("secret_key"),
        )

    changed = any(converted.get(u, u) != u for u in urls.values())
    return {
        "links": [
            {
                "ingredient": name,
                "naver": naver_shopping_url(name),
                "coupang": converted.get(url, url),
            }
            for name, url in urls.items()
        ],
        "earner": intended if changed else "none",
    }


def coupang_raw_search_url(ingredient_name: str) -> str:
    """변환 전의 쿠팡 검색 URL. 제휴 여부와 무관한 순수한 검색 주소다."""
    query = quote(ingredient_name.strip())
    return f"https://www.coupang.com/np/search?component=&q={query}&channel=user"


# ---------------------------------------------------------------------------
# [#95] 유저별 쿠팡파트너스 키 저장/조회/삭제 - 반드시 암호화해서 저장한다.
# ---------------------------------------------------------------------------

def save_user_coupang_key(cur, user_id: int, access_key: str, secret_key: str):
    """유저 본인의 쿠팡파트너스 키를 암호화해서 저장한다(이미 있으면 덮어쓴다)."""
    from crypto_utils import encrypt_value

    now = datetime.now().isoformat()
    cur.execute(
        """
        INSERT INTO user_partner_keys (user_id, coupang_access_key_encrypted, coupang_secret_key_encrypted, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            coupang_access_key_encrypted = excluded.coupang_access_key_encrypted,
            coupang_secret_key_encrypted = excluded.coupang_secret_key_encrypted,
            updated_at = excluded.updated_at
        """,
        (user_id, encrypt_value(access_key), encrypt_value(secret_key), now),
    )


def delete_user_coupang_key(cur, user_id: int):
    """유저가 본인 키 연동을 해제한다."""
    cur.execute("DELETE FROM user_partner_keys WHERE user_id = ?", (user_id,))


def get_user_coupang_key(cur, user_id: int) -> tuple[str | None, str | None]:
    """복호화된 (access_key, secret_key)를 돌려준다. 등록 안 했으면 (None, None)."""
    from crypto_utils import decrypt_value

    cur.execute(
        "SELECT coupang_access_key_encrypted, coupang_secret_key_encrypted "
        "FROM user_partner_keys WHERE user_id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None, None
    return decrypt_value(row[0]), decrypt_value(row[1])


def get_shopping_key_for_recipe(cur, recipe: dict) -> dict:
    """이 레시피의 재료 구매 링크에 누구 키를 쓸지 정한다 (#95).

    돌려주는 것:
        {"access_key", "secret_key", "earner": "site" | "author" | "none", "author_id": int | None}

    `earner`가 필요한 이유는 화면이 **누가 수수료를 받는지 밝혀야** 하기 때문이다.
    제휴 링크에는 대가성 고지가 붙어야 하는데, 유저 레시피에서는 그 주체가 사이트가
    아니라 작성자다. 판단을 한 곳에서만 하려고 키와 함께 돌려준다.

    기준이 노출과 다르다. 남에게 보이기 시작하는 것은 추천 USER_RECIPE_MIN_LIKES(3)회지만,
    수익이 작성자에게 넘어가는 것은 USER_RECIPE_REVENUE_MIN_LIKES(100)회다 - 추천 3회는
    지인 몇 명으로 만들 수 있어서 돈을 걸기에는 너무 낮다.
    """
    site = {"access_key": None, "secret_key": None, "earner": "site", "author_id": None}

    if not recipe or recipe.get("source_api") != "user":
        return site
    submitted_by = recipe.get("submitted_by")
    if not submitted_by:
        return site

    cur.execute("SELECT COUNT(*) FROM recipe_likes WHERE recipe_id = ?", (recipe["id"],))
    if cur.fetchone()[0] < USER_RECIPE_REVENUE_MIN_LIKES:
        return site

    access_key, secret_key = get_user_coupang_key(cur, submitted_by)
    if not access_key or not secret_key:
        # 기준은 넘었는데 키를 등록 안 했다. 사이트 키로 되돌리면 작성자 레시피의 수익을
        # 사이트가 가져가게 되므로 그렇게 하지 않는다. 아무 키도 없는 일반 검색 링크가 된다.
        return {"access_key": None, "secret_key": None, "earner": "none", "author_id": submitted_by}

    return {
        "access_key": access_key,
        "secret_key": secret_key,
        "earner": "author",
        "author_id": submitted_by,
    }
