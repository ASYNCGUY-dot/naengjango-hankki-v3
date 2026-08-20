"""
자랑하기(/brags)를 검증한다 (2026-08-20).

가장 조심할 곳은 **자랑 글 좋아요가 레시피 추천에 반영되는 규칙**이다. 사람당
레시피당 1회여야 한다 - 유저 등록 레시피의 공개 기준이 추천 3회인데
(recommendation_agent.USER_RECIPE_MIN_LIKES) 그 기준이 한 사람에게 휘둘리면 안 된다.
"""

import pytest
from helpers import signup_body


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json=signup_body(username))
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _post(client, user_id, headers, recipe_id=1, body="만들어봤어요. 맛있었습니다.", image_url=None):
    return client.post(
        "/brags",
        params={"user_id": user_id},
        json={"recipe_id": recipe_id, "body": body, "image_url": image_url},
        headers=headers,
    )


def _recipe_like_count(db_conn, recipe_id: int) -> int:
    return db_conn.execute(
        "SELECT COUNT(*) FROM recipe_likes WHERE recipe_id = ?", (recipe_id,)
    ).fetchone()[0]


def test_posting_a_brag_returns_it_with_the_recipe_name(client):
    user_id, headers = _signup(client, "u_brag_1")

    res = _post(client, user_id, headers)

    assert res.status_code == 200
    item = res.json()
    # 피드 카드가 "누가 어떤 메뉴를 만들었는지"를 그리려면 이 둘이 필요하다.
    assert item["menu_name"] == "두부조림"
    assert item["username"] == "u_brag_1"
    assert item["like_count"] == 0
    assert item["liked_by_me"] is False


def test_the_feed_is_readable_without_logging_in(client):
    """서버는 피드를 공개로 둔다. 다만 지금 화면은 로그인해야 열린다(AppLayout이 관문).

    지금 이 경로로 들어올 화면이 없다는 뜻이라, "비로그인도 볼 수 있다"를 제품의
    약속으로 읽으면 안 된다. 레시피 상세에 자랑 글을 붙이게 되면 그때 살아난다.
    """
    user_id, headers = _signup(client, "u_brag_2")
    _post(client, user_id, headers, body="비로그인도 보이는 글")

    res = client.get("/brags")

    assert res.status_code == 200
    assert [b["body"] for b in res.json()] == ["비로그인도 보이는 글"]
    # 누가 눌렀는지 모르니 전부 False여야 한다.
    assert all(b["liked_by_me"] is False for b in res.json())


def test_the_feed_is_newest_first(client):
    user_id, headers = _signup(client, "u_brag_3")
    _post(client, user_id, headers, body="먼저 쓴 글")
    _post(client, user_id, headers, body="나중에 쓴 글")

    bodies = [b["body"] for b in client.get("/brags").json()]

    assert bodies == ["나중에 쓴 글", "먼저 쓴 글"]


def test_liking_a_brag_also_recommends_its_recipe(client, db_conn):
    author_id, author_headers = _signup(client, "u_brag_4")
    brag_id = _post(client, author_id, author_headers).json()["id"]
    reader_id, reader_headers = _signup(client, "u_brag_5")

    res = client.post(
        f"/brags/{brag_id}/like/toggle", params={"user_id": reader_id}, headers=reader_headers
    )

    assert res.json() == {"liked": True, "like_count": 1}
    assert _recipe_like_count(db_conn, 1) == 1


def test_one_person_counts_once_per_recipe_no_matter_how_many_brags(client, db_conn):
    """같은 레시피로 쓴 글이 여럿이고 한 사람이 전부 좋아요를 눌러도 추천은 1회다.

    이걸 안 지키면 유저 등록 레시피의 공개 기준(추천 3회)을 한 사람이 혼자 채운다.
    """
    author_id, author_headers = _signup(client, "u_brag_6")
    first = _post(client, author_id, author_headers, body="첫 번째").json()["id"]
    second = _post(client, author_id, author_headers, body="두 번째").json()["id"]
    reader_id, reader_headers = _signup(client, "u_brag_7")

    for brag_id in (first, second):
        client.post(
            f"/brags/{brag_id}/like/toggle", params={"user_id": reader_id}, headers=reader_headers
        )

    assert _recipe_like_count(db_conn, 1) == 1


def test_unliking_one_brag_keeps_the_recipe_recommendation_if_another_is_still_liked(
    client, db_conn
):
    """마지막 하나를 뗄 때만 레시피 추천을 뗀다."""
    author_id, author_headers = _signup(client, "u_brag_8")
    first = _post(client, author_id, author_headers, body="첫 번째").json()["id"]
    second = _post(client, author_id, author_headers, body="두 번째").json()["id"]
    reader_id, reader_headers = _signup(client, "u_brag_9")
    for brag_id in (first, second):
        client.post(
            f"/brags/{brag_id}/like/toggle", params={"user_id": reader_id}, headers=reader_headers
        )

    client.post(
        f"/brags/{first}/like/toggle", params={"user_id": reader_id}, headers=reader_headers
    )
    assert _recipe_like_count(db_conn, 1) == 1, "다른 글에 아직 좋아요가 남아 있다"

    client.post(
        f"/brags/{second}/like/toggle", params={"user_id": reader_id}, headers=reader_headers
    )
    assert _recipe_like_count(db_conn, 1) == 0


def test_liking_a_brag_does_not_double_count_when_the_recipe_was_already_recommended(
    client, db_conn
):
    # 레시피 상세에서 이미 추천을 눌러 둔 사람이 자랑 글에도 좋아요를 누르는 경우.
    reader_id, reader_headers = _signup(client, "u_brag_10")
    client.post(
        "/recommendation/recipes/1/like/toggle", params={"user_id": reader_id}, headers=reader_headers
    )
    author_id, author_headers = _signup(client, "u_brag_11")
    brag_id = _post(client, author_id, author_headers).json()["id"]

    client.post(
        f"/brags/{brag_id}/like/toggle", params={"user_id": reader_id}, headers=reader_headers
    )

    assert _recipe_like_count(db_conn, 1) == 1


def test_deleting_my_brag_leaves_the_recipe_recommendation_alone(client, db_conn):
    # 글이 사라져도 "이 레시피를 좋게 봤다"는 남들의 판단까지 되돌릴 이유가 없다.
    author_id, author_headers = _signup(client, "u_brag_12")
    brag_id = _post(client, author_id, author_headers).json()["id"]
    reader_id, reader_headers = _signup(client, "u_brag_13")
    client.post(
        f"/brags/{brag_id}/like/toggle", params={"user_id": reader_id}, headers=reader_headers
    )

    res = client.delete(f"/brags/{brag_id}", params={"user_id": author_id}, headers=author_headers)

    assert res.status_code == 200
    assert client.get("/brags").json() == []
    assert _recipe_like_count(db_conn, 1) == 1


def test_i_cannot_delete_someone_elses_brag(client):
    author_id, author_headers = _signup(client, "u_brag_14")
    brag_id = _post(client, author_id, author_headers).json()["id"]
    other_id, other_headers = _signup(client, "u_brag_15")

    res = client.delete(f"/brags/{brag_id}", params={"user_id": other_id}, headers=other_headers)

    assert res.status_code == 404
    assert len(client.get("/brags").json()) == 1


def test_posting_about_a_recipe_that_does_not_exist_is_rejected(client):
    user_id, headers = _signup(client, "u_brag_16")

    res = _post(client, user_id, headers, recipe_id=999999)

    assert res.status_code == 404


@pytest.mark.parametrize("body", ["", "가" * 1001])
def test_body_limits_are_enforced_by_the_server(client, body):
    user_id, headers = _signup(client, f"u_brag_limit_{len(body)}")

    assert _post(client, user_id, headers, body=body).status_code == 422


@pytest.mark.parametrize("method,path", [("post", ""), ("delete", "/1"), ("post", "/1/like/toggle")])
def test_writing_requires_a_token(client, method, path):
    res = client.request(
        method, f"/brags{path}", params={"user_id": 1}, json={"recipe_id": 1, "body": "x"}
    )
    assert res.status_code == 401


def test_posting_a_brag_is_logged(client, db_conn):
    """"만들어봤다"는 이 앱의 최종 목표에 닿은 유일한 신호라 이탈 분석에서 따로 센다."""
    user_id, headers = _signup(client, "u_brag_17")

    _post(client, user_id, headers)

    events = db_conn.execute(
        "SELECT event FROM usage_events WHERE user_id = ?", (user_id,)
    ).fetchall()
    assert ("brag_post",) in events


# ---------- 사진 업로드 ----------

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 40


def _upload(client, user_id, headers, content: bytes, filename="photo.jpg", mime="image/jpeg"):
    return client.post(
        "/brags/photo",
        params={"user_id": user_id},
        files={"file": (filename, content, mime)},
        headers=headers,
    )


@pytest.mark.parametrize("content", [JPEG, PNG, WEBP])
def test_detect_image_accepts_the_three_formats_we_allow(content):
    from src.agents import storage_agent

    assert storage_agent.detect_image(content) is not None


def test_detect_image_rejects_a_file_that_only_claims_to_be_an_image():
    """확장자와 Content-Type은 둘 다 위조할 수 있다. 실제 바이트로 판별한다."""
    from src.agents import storage_agent

    assert storage_agent.detect_image(b"<?php system($_GET['c']); ?>") is None


def test_uploading_a_non_image_is_rejected_even_with_an_image_content_type(
    client, monkeypatch
):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test")
    user_id, headers = _signup(client, "u_brag_up_1")

    res = _upload(client, user_id, headers, b"<?php echo 1; ?>", "hack.jpg", "image/jpeg")

    assert res.status_code == 415


def test_uploading_something_too_large_is_rejected(client, monkeypatch):
    from src.agents import storage_agent

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test")
    user_id, headers = _signup(client, "u_brag_up_2")

    too_big = JPEG + b"\x00" * storage_agent.MAX_BYTES
    res = _upload(client, user_id, headers, too_big)

    assert res.status_code == 413


def test_upload_says_so_when_the_store_is_not_configured(client, monkeypatch):
    # 사진 없이 글만 올리는 것은 정상 동작이라, 저장소가 없다고 자랑하기 전체가
    # 죽으면 안 된다. 이 엔드포인트만 503으로 답한다.
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    user_id, headers = _signup(client, "u_brag_up_3")

    assert _upload(client, user_id, headers, JPEG).status_code == 503


def test_upload_requires_a_token(client):
    res = client.post("/brags/photo", params={"user_id": 1}, files={"file": ("a.jpg", JPEG, "image/jpeg")})
    assert res.status_code == 401


def test_upload_path_does_not_use_the_name_the_user_sent(monkeypatch):
    """사용자가 준 이름을 경로에 쓰면 경로 조작이 되고 같은 이름이 서로를 덮어쓴다."""
    from src.agents import storage_agent

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test")
    sent: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

    def fake_post(url, **kwargs):
        sent["url"] = url
        return FakeResponse()

    monkeypatch.setattr(storage_agent.requests, "post", fake_post)

    url = storage_agent.upload_image(JPEG, user_id=116)

    assert "../" not in sent["url"]
    assert sent["url"].endswith(".jpg")
    # 누가 올렸는지는 경로에 남는다 - 나중에 한 사람 것만 지우기 쉽게.
    assert "/brag-photos/116/" in sent["url"]
    assert url is not None and "/object/public/brag-photos/116/" in url
