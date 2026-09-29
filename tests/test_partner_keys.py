"""유저별 제휴 키와 수익 귀속을 검증한다 (2026-09-11, #95).

여기는 **돈이 누구에게 가는지**를 정하는 코드다. 다른 데서 틀리면 화면이 이상해지고 말지만
여기서 틀리면 수수료가 엉뚱한 사람에게 간다. 그래서 경계를 전부 고정한다.

특히 지키려는 것 셋:

1. 저장한 키는 어떤 응답에도 실리지 않는다.
2. 남의 키를 만지지 못한다(관리자도 마찬가지다).
3. 수익 귀속 기준은 노출 기준(3)이 아니라 수익 기준(100)이다. 이걸 섞으면 지인 셋만
   모으면 남의 재료 구매로 돈을 벌 수 있다.
"""

import os

import pytest
from helpers import signup_body

from src.agents import shopping_agent
from src.agents.recommendation_agent import (
    USER_RECIPE_MIN_LIKES,
    USER_RECIPE_REVENUE_MIN_LIKES,
)

# crypto_utils는 이 키가 없으면 예외를 낸다. 테스트용 고정 키를 쓰고, 운영 키와 겹치지
# 않도록 여기서만 세팅한다.
os.environ.setdefault("APP_ENCRYPTION_KEY", "8ZDfM2sO7WQK1kkr0Zx4nnQvJZKMEnJJtnwZ6bcHQDs=")


@pytest.fixture(autouse=True)
def _reset_cooldown():
    """변환 실패 기록은 모듈 전역이라 테스트 사이에 남는다.

    지금은 테스트마다 다른 키를 써서 우연히 안 겹치지만, 같은 키를 쓰는 테스트를 하나
    추가하는 순간 "왜 호출을 안 하지"로 나타난다. 매번 비우고 시작한다.
    """
    shopping_agent._last_failure_at.clear()
    yield
    shopping_agent._last_failure_at.clear()


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json=signup_body(username))
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


# ---------------------------------------------------------------------------
# 키 등록·조회·해제
# ---------------------------------------------------------------------------

def test_register_then_status_says_registered(client):
    user_id, headers = _signup(client, "partner1")

    res = client.get(f"/partner-keys/{user_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["registered"] is False

    res = client.put(
        f"/partner-keys/{user_id}",
        json={"access_key": "ak-abcdefgh", "secret_key": "sk-abcdefgh"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["registered"] is True

    res = client.get(f"/partner-keys/{user_id}", headers=headers)
    assert res.json()["registered"] is True
    assert res.json()["updated_at"]


def test_stored_keys_never_come_back_in_any_response(client):
    """키가 응답에 실리면 로그·캐시·브라우저 히스토리로 새어나갈 자리가 늘어난다."""
    user_id, headers = _signup(client, "partner2")
    secret = "sk-supersecret-value"

    put = client.put(
        f"/partner-keys/{user_id}",
        json={"access_key": "ak-abcdefgh", "secret_key": secret},
        headers=headers,
    )
    get = client.get(f"/partner-keys/{user_id}", headers=headers)

    for res in (put, get):
        assert secret not in res.text
        assert "ak-abcdefgh" not in res.text


def test_keys_are_encrypted_at_rest(client, db_conn):
    user_id, headers = _signup(client, "partner3")
    secret = "sk-supersecret-value"
    client.put(
        f"/partner-keys/{user_id}",
        json={"access_key": "ak-abcdefgh", "secret_key": secret},
        headers=headers,
    )

    row = db_conn.execute(
        "SELECT coupang_access_key_encrypted, coupang_secret_key_encrypted "
        "FROM user_partner_keys WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    assert secret not in row[1]
    assert "ak-abcdefgh" not in row[0]


def test_delete_removes_the_key(client, db_conn):
    user_id, headers = _signup(client, "partner4")
    client.put(
        f"/partner-keys/{user_id}",
        json={"access_key": "ak-abcdefgh", "secret_key": "sk-abcdefgh"},
        headers=headers,
    )

    res = client.delete(f"/partner-keys/{user_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["registered"] is False
    assert db_conn.execute(
        "SELECT COUNT(*) FROM user_partner_keys WHERE user_id = ?", (user_id,)
    ).fetchone()[0] == 0


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_cannot_touch_another_users_keys(client, method):
    """남의 제휴 수익 계정을 만질 수 있으면 안 된다. 관리자도 예외가 아니다."""
    victim_id, _ = _signup(client, "partner_victim")
    _, attacker_headers = _signup(client, "partner_attacker")

    kwargs = {"headers": attacker_headers}
    if method == "put":
        kwargs["json"] = {"access_key": "ak-abcdefgh", "secret_key": "sk-abcdefgh"}
    res = getattr(client, method)(f"/partner-keys/{victim_id}", **kwargs)
    assert res.status_code == 403


def test_requires_authentication(client):
    user_id, _ = _signup(client, "partner5")
    assert client.get(f"/partner-keys/{user_id}").status_code == 401


# ---------------------------------------------------------------------------
# 수익 귀속 판단
# ---------------------------------------------------------------------------

def test_official_recipe_uses_site_key(db_conn):
    cur = db_conn.cursor()
    info = shopping_agent.get_shopping_key_for_recipe(cur, {"id": 1, "source_api": "COOKRCP01"})
    assert info["earner"] == "site"
    assert info["author_id"] is None


def test_revenue_threshold_is_higher_than_the_visibility_threshold():
    """둘이 같아지면 지인 셋만 모아도 남의 재료 구매로 돈을 벌 수 있다."""
    assert USER_RECIPE_REVENUE_MIN_LIKES > USER_RECIPE_MIN_LIKES


def _make_user_recipe(db_conn, author_id: int, likes: int, recipe_id: int = 9001):
    db_conn.execute(
        "INSERT INTO recipes (id, menu_name, source_api, submitted_by, status) "
        "VALUES (?, '테스트 유저 레시피', 'user', ?, 'approved')",
        (recipe_id, author_id),
    )
    for i in range(likes):
        db_conn.execute(
            "INSERT INTO recipe_likes (recipe_id, user_id, created_at) VALUES (?, ?, '2026-09-11')",
            (recipe_id, 100000 + i),
        )
    return {"id": recipe_id, "source_api": "user", "submitted_by": author_id}


def test_user_recipe_below_revenue_threshold_uses_site_key(client, db_conn):
    """노출 기준(3)은 넘었지만 수익 기준(100) 아래면 아직 사이트 키다."""
    author_id, headers = _signup(client, "author_low")
    client.put(
        f"/partner-keys/{author_id}",
        json={"access_key": "ak-abcdefgh", "secret_key": "sk-abcdefgh"},
        headers=headers,
    )
    recipe = _make_user_recipe(db_conn, author_id, likes=USER_RECIPE_MIN_LIKES)

    info = shopping_agent.get_shopping_key_for_recipe(db_conn.cursor(), recipe)
    assert info["earner"] == "site"


def test_user_recipe_above_revenue_threshold_uses_author_key(client, db_conn):
    author_id, headers = _signup(client, "author_high")
    client.put(
        f"/partner-keys/{author_id}",
        json={"access_key": "ak-abcdefgh", "secret_key": "sk-secretvalue"},
        headers=headers,
    )
    recipe = _make_user_recipe(db_conn, author_id, likes=USER_RECIPE_REVENUE_MIN_LIKES)

    info = shopping_agent.get_shopping_key_for_recipe(db_conn.cursor(), recipe)
    assert info["earner"] == "author"
    assert info["author_id"] == author_id
    assert info["secret_key"] == "sk-secretvalue"


def test_promoted_author_without_a_key_gets_no_affiliate_link(client, db_conn):
    """사이트 키로 되돌리면 작성자 레시피의 수익을 사이트가 가져가게 된다. 그렇게 안 한다."""
    author_id, _ = _signup(client, "author_nokey")
    recipe = _make_user_recipe(db_conn, author_id, likes=USER_RECIPE_REVENUE_MIN_LIKES)

    info = shopping_agent.get_shopping_key_for_recipe(db_conn.cursor(), recipe)
    assert info["earner"] == "none"
    assert info["access_key"] is None


def test_earner_none_does_not_fall_back_to_the_site_key(monkeypatch):
    """`earner`가 "none"이면 변환 자체를 시도하지 않아야 한다.

    사이트 키가 **설정돼 있을 때**만 드러나는 규칙이라 여기서 일부러 넣어준다. 키가
    비어 있으면 어느 쪽 코드든 원본 URL을 돌려줘서 차이가 안 보인다 - 실제로 이 테스트
    없이는 "사이트 키로 되돌리기"가 뮤테이션에서 살아남았다.
    """
    calls = []

    def record(*args, **kwargs):
        calls.append(kwargs.get("json"))
        raise RuntimeError("여기까지 오면 안 된다")

    monkeypatch.setattr(shopping_agent, "COUPANG_ACCESS_KEY", "site-ak")
    monkeypatch.setattr(shopping_agent, "COUPANG_SECRET_KEY", "site-sk")
    monkeypatch.setattr(shopping_agent.requests, "post", record)

    none_info = {"access_key": None, "secret_key": None, "earner": "none", "author_id": 7}
    url = shopping_agent.coupang_search_url("양파", none_info)
    assert url.startswith("https://www.coupang.com/np/search")
    assert calls == [], "earner=none인데 쿠팡 변환을 시도했다(사이트 키가 붙는다)"

    # 반대쪽도 확인한다. key_info가 없으면 사이트 키로 변환을 시도해야 한다.
    shopping_agent.coupang_search_url("양파", None)
    assert len(calls) == 1, "사이트 기본 경로에서는 변환을 시도해야 한다"


# ---------------------------------------------------------------------------
# 링크 생성
# ---------------------------------------------------------------------------

def test_links_are_made_for_both_stores():
    links = shopping_agent.get_shopping_links("깻잎")
    assert "search.shopping.naver.com" in links["naver"]
    assert "coupang.com" in links["coupang"]
    # 재료명이 URL 인코딩돼 들어가야 한다. 한글을 그대로 붙이면 링크가 깨진다.
    assert "%EA%B9%BB%EC%9E%8E" in links["naver"]


def test_conversion_failure_falls_back_to_the_original_url(monkeypatch):
    """이 함수는 화면을 그리는 경로 한가운데 있다. 여기서 예외가 나면 부족한 재료
    목록 자체가 안 보인다. 수수료를 못 받는 것보다 그쪽이 나쁘다."""
    def boom(*args, **kwargs):
        raise RuntimeError("쿠팡 API 죽음")

    monkeypatch.setattr(shopping_agent.requests, "post", boom)
    url = shopping_agent.convert_to_coupang_partner_link(
        "https://www.coupang.com/np/search?q=양파", "ak-test", "sk-test"
    )
    assert url == "https://www.coupang.com/np/search?q=양파"


def test_signature_follows_the_documented_format():
    """서명 대상은 datetime + method + path + query 순서이고 HmacSHA256 hexdigest다.
    쿠팡 공식 문서(2026-09-11 확인) 기준. 순서가 틀리면 전부 401로 돌아온다."""
    import hashlib
    import hmac

    header = shopping_agent._coupang_authorization("POST", "/some/path", "", "AK", "SK")

    assert header.startswith("CEA algorithm=HmacSHA256, access-key=AK, signed-date=")
    signed_date = header.split("signed-date=")[1].split(",")[0]
    expected = hmac.new(
        b"SK", (signed_date + "POST" + "/some/path" + "").encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert header.endswith(f"signature={expected}")


def test_signed_date_is_utc():
    """포맷의 Z는 UTC를 뜻한다. 로컬시간으로 만들면 시간대가 다른 환경에서 서명이 거절된다.
    쿠팡 공식 예제가 로컬시간을 쓰고 있어서 그대로 베끼면 여기서 걸린다."""
    import re
    from datetime import datetime, timezone

    header = shopping_agent._coupang_authorization("POST", "/p", "", "AK", "SK")
    signed_date = header.split("signed-date=")[1].split(",")[0]
    assert re.fullmatch(r"\d{6}T\d{6}Z", signed_date)
    assert signed_date[:6] == datetime.now(timezone.utc).strftime("%y%m%d")


# ---------------------------------------------------------------------------
# 여러 재료를 한 번에 (배치)와 고지 정확성
# ---------------------------------------------------------------------------

def test_many_ingredients_make_one_conversion_request(monkeypatch):
    """재료마다 부르면 부족한 재료가 일곱 개일 때 타임아웃도 일곱 배가 된다."""
    calls = []

    def record(*args, **kwargs):
        calls.append(kwargs.get("json", {}).get("coupangUrls"))
        raise RuntimeError("승인 전")

    monkeypatch.setattr(shopping_agent, "COUPANG_ACCESS_KEY", "site-ak")
    monkeypatch.setattr(shopping_agent, "COUPANG_SECRET_KEY", "site-sk")
    monkeypatch.setattr(shopping_agent.requests, "post", record)

    shopping_agent.get_shopping_links_for(["양파", "대파", "마늘", "간장"])

    assert len(calls) == 1, f"요청이 {len(calls)}번 나갔다. 한 번으로 묶여야 한다"
    assert len(calls[0]) == 4, "네 재료의 URL이 한 요청에 다 실려야 한다"


def test_failure_puts_the_key_in_cooldown(monkeypatch):
    """승인 전 키는 항상 실패한다. 매번 5초를 다시 기다리면 화면이 그만큼 멈춘다."""
    calls = []

    def record(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("승인 전")

    monkeypatch.setattr(shopping_agent, "COUPANG_ACCESS_KEY", "site-ak")
    monkeypatch.setattr(shopping_agent, "COUPANG_SECRET_KEY", "site-sk")
    monkeypatch.setattr(shopping_agent.requests, "post", record)

    shopping_agent.get_shopping_links_for(["양파"])
    shopping_agent.get_shopping_links_for(["대파"])
    shopping_agent.get_shopping_links_for(["마늘"])

    assert len(calls) == 1, "첫 실패 뒤에는 한동안 다시 시도하지 않아야 한다"


def test_cooldown_does_not_store_the_key_in_plain_text(monkeypatch):
    monkeypatch.setattr(shopping_agent, "COUPANG_ACCESS_KEY", "site-ak-plain")
    monkeypatch.setattr(shopping_agent, "COUPANG_SECRET_KEY", "site-sk")
    monkeypatch.setattr(shopping_agent.requests, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))

    shopping_agent.get_shopping_links_for(["양파"])

    assert "site-ak-plain" not in shopping_agent._last_failure_at


def test_earner_reports_what_actually_happened_not_the_intent(monkeypatch):
    """고지가 거짓말을 하면 안 된다.

    변환이 실패하면 링크는 그냥 검색 URL인데, earner가 "작정"을 그대로 들고 있으면
    화면이 "아무개님에게 수수료가 갑니다"라고 적는다. 아무도 못 받는 돈이다.
    """
    monkeypatch.setattr(shopping_agent, "COUPANG_ACCESS_KEY", "site-ak")
    monkeypatch.setattr(shopping_agent, "COUPANG_SECRET_KEY", "site-sk")
    monkeypatch.setattr(shopping_agent.requests, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))

    result = shopping_agent.get_shopping_links_for(
        ["양파"], {"access_key": "ak", "secret_key": "sk", "earner": "author", "author_id": 7}
    )
    assert result["earner"] == "none"


def test_earner_stays_when_conversion_actually_worked(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"originalUrl": shopping_agent.coupang_raw_search_url("양파"),
                     "shortenUrl": "https://link.coupang.com/a/SHORT"}
                ]
            }

    monkeypatch.setattr(shopping_agent, "COUPANG_ACCESS_KEY", "site-ak")
    monkeypatch.setattr(shopping_agent, "COUPANG_SECRET_KEY", "site-sk")
    monkeypatch.setattr(shopping_agent.requests, "post", lambda *a, **k: FakeResponse())

    result = shopping_agent.get_shopping_links_for(
        ["양파"], {"access_key": "ak", "secret_key": "sk", "earner": "author", "author_id": 7}
    )
    assert result["earner"] == "author"
    assert result["links"][0]["coupang"] == "https://link.coupang.com/a/SHORT"


def test_response_order_is_not_assumed(monkeypatch):
    """응답이 보낸 순서대로 온다고 가정하면 재료와 링크가 뒤바뀐다."""
    onion = shopping_agent.coupang_raw_search_url("양파")
    leek = shopping_agent.coupang_raw_search_url("대파")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            # 일부러 뒤집어서 준다.
            return {
                "data": [
                    {"originalUrl": leek, "shortenUrl": "https://link/LEEK"},
                    {"originalUrl": onion, "shortenUrl": "https://link/ONION"},
                ]
            }

    monkeypatch.setattr(shopping_agent, "COUPANG_ACCESS_KEY", "site-ak")
    monkeypatch.setattr(shopping_agent, "COUPANG_SECRET_KEY", "site-sk")
    monkeypatch.setattr(shopping_agent.requests, "post", lambda *a, **k: FakeResponse())

    result = shopping_agent.get_shopping_links_for(["양파", "대파"])
    by_name = {link["ingredient"]: link["coupang"] for link in result["links"]}
    assert by_name["양파"] == "https://link/ONION"
    assert by_name["대파"] == "https://link/LEEK"


def test_status_tells_the_screen_the_threshold(client):
    """화면이 기준 숫자를 따로 들고 있으면 기준이 바뀔 때 조용히 어긋난다."""
    user_id, headers = _signup(client, "partner_threshold")
    res = client.get(f"/partner-keys/{user_id}", headers=headers)
    assert res.json()["revenue_min_likes"] == USER_RECIPE_REVENUE_MIN_LIKES


# ---------------------------------------------------------------------------
# 본인 제휴 링크 (2026-09-15)
#
# 쿠팡파트너스는 본인 링크로 본인이 구매하는 것을 수수료에서 빼고 계정 정지·수익 회수
# 사유로 다룬다(공식 가이드는 로그인 뒤라 직접 확인 못 했고 여러 2차 출처가 일치한다).
# 이 앱이 작성자에게 자기 링크를 내밀면 작성자 계정을 위험에 빠뜨리는 셈이다.
# ---------------------------------------------------------------------------

def test_author_does_not_see_their_own_affiliate_link(client, db_conn):
    author_id, headers = _signup(client, "author_self")
    client.put(
        f"/partner-keys/{author_id}",
        json={"access_key": "ak-abcdefgh", "secret_key": "sk-abcdefgh"},
        headers=headers,
    )
    recipe = _make_user_recipe(db_conn, author_id, likes=USER_RECIPE_REVENUE_MIN_LIKES, recipe_id=9101)

    info = shopping_agent.get_shopping_key_for_recipe(db_conn.cursor(), recipe, viewer_id=author_id)
    assert info["earner"] == "none"
    # 쓰지 않을 비밀을 꺼내지 않는다.
    assert info["access_key"] is None and info["secret_key"] is None


def test_someone_else_still_gets_the_authors_link(client, db_conn):
    """막는 것은 작성자 본인뿐이다. 다른 사람에게까지 막으면 이 기능이 통째로 꺼진다."""
    author_id, headers = _signup(client, "author_for_others")
    viewer_id, _ = _signup(client, "viewer_other")
    client.put(
        f"/partner-keys/{author_id}",
        json={"access_key": "ak-abcdefgh", "secret_key": "sk-abcdefgh"},
        headers=headers,
    )
    recipe = _make_user_recipe(db_conn, author_id, likes=USER_RECIPE_REVENUE_MIN_LIKES, recipe_id=9102)

    info = shopping_agent.get_shopping_key_for_recipe(db_conn.cursor(), recipe, viewer_id=viewer_id)
    assert info["earner"] == "author"


def test_admin_does_not_see_the_site_affiliate_link(client, db_conn):
    """사이트 키는 운영자 본인 계정의 것이라 같은 이유로 막는다."""
    admin_id, _ = _signup(client, "admin_self")
    db_conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (admin_id,))

    info = shopping_agent.get_shopping_key_for_recipe(
        db_conn.cursor(), {"id": 1, "source_api": "COOKRCP01"}, viewer_id=admin_id
    )
    assert info["earner"] == "none"


def test_regular_user_still_gets_the_site_link(client, db_conn):
    user_id, _ = _signup(client, "regular_viewer")
    info = shopping_agent.get_shopping_key_for_recipe(
        db_conn.cursor(), {"id": 1, "source_api": "COOKRCP01"}, viewer_id=user_id
    )
    assert info["earner"] == "site"


def test_shopping_links_route_passes_the_viewer(client, monkeypatch):
    """판단 함수가 옳아도 라우터가 보는 사람을 안 넘기면 규칙이 통째로 꺼진다."""
    user_id, headers = _signup(client, "route_viewer")
    seen = {}
    real = shopping_agent.get_shopping_key_for_recipe

    def spy(cur, recipe, viewer_id=None):
        seen["viewer_id"] = viewer_id
        return real(cur, recipe, viewer_id=viewer_id)

    monkeypatch.setattr(shopping_agent, "get_shopping_key_for_recipe", spy)
    res = client.get(
        "/recommendation/recipes/1/shopping-links", params={"user_id": user_id}, headers=headers
    )
    assert res.status_code == 200, res.text
    assert seen.get("viewer_id") == user_id
