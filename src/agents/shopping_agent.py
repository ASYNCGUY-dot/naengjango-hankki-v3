"""
Shopping Agent [확장] - 부족한 재료 구매 링크 (#79)
- 역할: 재료명으로 "네이버쇼핑"/"쿠팡" 검색 결과 페이지로 바로 이동하는 링크(URL)를 만든다.
- 공식 쇼핑 API 연동은 이번 프로젝트 범위에서는 어려워서(지침 6번 데이터 소스 표 참고),
  대신 각 사이트의 검색 URL 패턴에 재료명만 넣어서 "검색 결과 페이지" 링크를 만드는 방식이다
  (API 키·인증 없이 URL만으로 동작).
- 주의: 실제 상품·가격·재고는 보장하지 않는다. 사용자가 검색 결과를 보고 직접 판단해야 한다.

[중요 - 지금은 수익(제휴 수수료) 연결이 안 되는 상태, #93 참고]
아래 링크는 그냥 "검색해주는" 일반 URL이라, 유저가 눌러서 실제로 구매해도 이 프로젝트에는
수수료가 들어오지 않는다. 검색해보니(2026-07) 쿠팡파트너스는 URL에 파라미터 하나 붙인다고
되는 게 아니라, 반드시 (1) 파트너스 사이트의 "간편 링크 만들기" 도구로 원본 URL을 변환하거나
(2) 정식 승인 후 발급받는 Deeplink API(인증키로 서명해서 원본 URL -> 트래킹 링크로 변환)를
거쳐야 실제로 수수료가 잡히는 링크가 된다. 네이버쇼핑도 마찬가지로 보통 판매자별 개별 제휴라
검색결과 페이지 자체에 붙이는 범용 셀프서비스 파라미터가 없는 경우가 많다 - 네이버 파트너스
센터에서 정확한 연동 방식을 확인해야 한다.

그래서 실제 흐름은 이렇다:
1) 쿠팡파트너스에 가입하고 승인을 받는다 (지금 당장 가능, 비용 없음).
2) 승인 후 Access Key/Secret Key를 발급받아 .env에 COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY로
   넣는다.
3) 아래 convert_to_coupang_partner_link()에 실제 Deeplink API 호출(HMAC 서명 인증)을 채워
   넣으면, get_shopping_links()를 호출하는 모든 화면(레시피 상세, 내 냉장고)에 자동으로
   적용된다 - 이 파일 하나만 고치면 된다.
지금은 승인 전이라 이 함수가 원본 URL을 그대로 돌려주는 상태(=지금과 동일하게 동작)로 뒀다.
"""

import os
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv

# 다른 agent들(ingredient_agent.py 등)과 같은 방식: .env 파일에 적어둔 값을 os.environ으로
# 불러온다. .env는 프로젝트 최상위 폴더(app.py와 같은 위치)에 있는 파일이다.
load_dotenv()

# 사이트 기본 키(지수님 본인 계정) - 공식 레시피 및 아직 크리에이터 본인 키를 등록 안 한
# 유저 레시피의 구매 링크에는 전부 이 키가 쓰인다.
COUPANG_ACCESS_KEY = os.getenv("COUPANG_ACCESS_KEY")
COUPANG_SECRET_KEY = os.getenv("COUPANG_SECRET_KEY")

# [#95] 유저 레시피가 정식 레시피로 승격될 때(추천 이 개수 이상), 그 유저가 본인 쿠팡파트너스
# 키를 등록했으면 사이트 기본 키 대신 그 키를 쓴다. recommendation_agent.USER_RECIPE_MIN_LIKES와
# 반드시 같은 값을 써야 하므로, 여기서 새로 정의하지 않고 그대로 가져다 쓴다.
from recommendation_agent import USER_RECIPE_MIN_LIKES  # noqa: E402


def convert_to_coupang_partner_link(url: str, access_key: str | None = None, secret_key: str | None = None) -> str:
    """
    [TODO - 쿠팡파트너스 승인 후 구현] 원본 쿠팡 URL을 실제 수수료가 잡히는 트래킹 링크로
    바꿔주는 자리. access_key/secret_key를 안 주면 사이트 기본 키를 쓰고, 레시피 주인이 본인
    키를 등록해뒀으면(#95) 호출하는 쪽에서 그 키를 넘겨받아 이 함수가 그 키로 변환한다.
    지금은 어느 키든 실제 API 연동이 안 돼있어서(가입/구현 전) 원본 URL을 그대로 돌려준다
    (기존과 동일 동작, 안전하게 아무것도 안 깨짐). 나중에 Deeplink API를 여기에 구현하면,
    사이트 기본 키든 유저 개인 키든 이 함수 하나만 고치면 전부 자동 적용된다.
    """
    access_key = access_key or COUPANG_ACCESS_KEY
    secret_key = secret_key or COUPANG_SECRET_KEY
    if not access_key or not secret_key:
        return url
    # 여기에 실제 Deeplink API 호출을 구현하면 됨 (아직 미구현 - 키가 없어서 테스트 불가).
    return url


def naver_shopping_url(ingredient_name: str) -> str:
    """네이버쇼핑 검색 결과 페이지 링크를 만든다. (아직 제휴 링크 아님 - 위 설명 참고)"""
    query = quote(ingredient_name.strip())
    return f"https://search.shopping.naver.com/search/all?query={query}"


def coupang_search_url(ingredient_name: str, access_key: str | None = None, secret_key: str | None = None) -> str:
    """쿠팡 검색 결과 페이지 링크를 만든다. 제휴 키가 준비되면 자동으로 트래킹 링크로 바뀐다."""
    query = quote(ingredient_name.strip())
    url = f"https://www.coupang.com/np/search?component=&q={query}&channel=user"
    return convert_to_coupang_partner_link(url, access_key, secret_key)


def get_shopping_links(ingredient_name: str, access_key: str | None = None, secret_key: str | None = None) -> dict:
    """
    화면에서 한 번에 쓰기 쉽게, 이 재료의 쇼핑 링크들을 dict로 묶어서 반환한다.
    access_key/secret_key: 특정 레시피 주인의 키를 쓰고 싶을 때만 넘긴다(get_shopping_key_for_recipe()
    참고). 안 넘기면 사이트 기본 키가 쓰인다(공식 레시피, 내 냉장고 화면 등 레시피와 무관한 곳).
    """
    return {
        "naver": naver_shopping_url(ingredient_name),
        "coupang": coupang_search_url(ingredient_name, access_key, secret_key),
    }


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


def has_user_coupang_key(cur, user_id: int) -> bool:
    access_key, secret_key = get_user_coupang_key(cur, user_id)
    return bool(access_key and secret_key)


def get_shopping_key_for_recipe(cur, recipe: dict) -> tuple[str | None, str | None]:
    """
    이 레시피의 재료 구매 링크에 누구 키를 쓸지 정한다 (#95).
    - 유저가 등록한 레시피(source_api == "user")이고, 정식 레시피로 승격됐고(추천
      USER_RECIPE_MIN_LIKES회 이상), 그 유저가 본인 키를 등록해뒀으면 -> 그 키.
    - 그 외(공식 레시피, 아직 미승격, 키 미등록)에는 (None, None)을 돌려준다 - 호출하는 쪽에서
      get_shopping_links()에 그대로 넘기면 자동으로 사이트 기본 키가 쓰인다.
    """
    if not recipe or recipe.get("source_api") != "user":
        return None, None
    submitted_by = recipe.get("submitted_by")
    if not submitted_by:
        return None, None
    cur.execute("SELECT COUNT(*) FROM recipe_likes WHERE recipe_id = ?", (recipe["id"],))
    like_count = cur.fetchone()[0]
    if like_count < USER_RECIPE_MIN_LIKES:
        return None, None
    return get_user_coupang_key(cur, submitted_by)
