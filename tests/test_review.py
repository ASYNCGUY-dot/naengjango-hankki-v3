"""
/reviews/{recipe_id} GET·POST, /reviews/{recipe_id}/summary를 검증한다.

summarize_reviews()는 OpenAI를 실제로 호출하는 review_agent._call_openai_summary를 쓴다 -
테스트에서 진짜 LLM을 부르면 느리고 비용도 들고 CI에 OPENAI_API_KEY가 없어 실패하므로,
_call_openai_summary를 monkeypatch로 대체해서 호출 여부/캐싱 로직만 검증한다(실제 요약
문장의 품질은 프롬프트 몫이라 이 테스트의 관심사가 아니다).
"""

from src.agents import review_agent

RECIPE_ID = 1  # seed.sql "두부조림"

TINY_PNG_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQ"
    "VR42mNk+P+/HgAFhAJ/wlseKgAAAABJRU5ErkJggg=="
)


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def test_create_review_nonexistent_recipe_returns_404(client):
    user_id, headers = _signup(client, "u_review_1")
    res = client.post(
        "/reviews/999999",
        json={"user_id": user_id, "rating": 5, "review_text": "맛있어요"},
        headers=headers,
    )
    assert res.status_code == 404


def test_create_review_as_other_user_returns_403(client):
    _, headers = _signup(client, "u_review_imposter")
    res = client.post(
        f"/reviews/{RECIPE_ID}",
        json={"user_id": 999999999, "rating": 5, "review_text": "맛있어요"},
        headers=headers,
    )
    assert res.status_code == 403


def test_create_review_rating_out_of_range_returns_422(client):
    user_id, headers = _signup(client, "u_review_2")
    res = client.post(f"/reviews/{RECIPE_ID}", json={"user_id": user_id, "rating": 0, "review_text": "별로"}, headers=headers)
    assert res.status_code == 422
    res = client.post(f"/reviews/{RECIPE_ID}", json={"user_id": user_id, "rating": 6, "review_text": "최고"}, headers=headers)
    assert res.status_code == 422


def test_create_and_list_review_with_photo(client):
    user_id, headers = _signup(client, "u_review_3")
    create_res = client.post(
        f"/reviews/{RECIPE_ID}",
        json={"user_id": user_id, "rating": 4, "review_text": "사진 첨부해요", "image_url": TINY_PNG_DATA_URI},
        headers=headers,
    )
    assert create_res.status_code == 200
    assert create_res.json() == {"saved": True}

    list_res = client.get(f"/reviews/{RECIPE_ID}")
    assert list_res.status_code == 200
    reviews = list_res.json()
    assert len(reviews) == 1
    assert reviews[0]["image_url"] == TINY_PNG_DATA_URI
    assert reviews[0]["rating"] == 4
    assert reviews[0]["username"] == "u_review_3"


def test_create_review_without_photo_has_null_image_url(client):
    user_id, headers = _signup(client, "u_review_4")
    client.post(f"/reviews/{RECIPE_ID}", json={"user_id": user_id, "rating": 5, "review_text": "좋아요"}, headers=headers)
    reviews = client.get(f"/reviews/{RECIPE_ID}").json()
    assert reviews[0]["image_url"] is None


def test_summary_with_no_reviews_returns_none_without_calling_llm(client, monkeypatch):
    def _fail_if_called(prompt):
        raise AssertionError("후기가 없으면 LLM을 호출하면 안 된다")

    monkeypatch.setattr(review_agent, "_call_openai_summary", _fail_if_called)
    res = client.get(f"/reviews/{RECIPE_ID}/summary")
    assert res.status_code == 200
    assert res.json() == {"summary": None}


def test_summary_calls_llm_once_then_uses_cache(client, monkeypatch):
    call_count = {"n": 0}

    def _fake_summary(prompt):
        call_count["n"] += 1
        return "• 가짜 요약 첫째 줄\n• 가짜 요약 둘째 줄"

    monkeypatch.setattr(review_agent, "_call_openai_summary", _fake_summary)
    user_id, headers = _signup(client, "u_review_5")
    client.post(f"/reviews/{RECIPE_ID}", json={"user_id": user_id, "rating": 5, "review_text": "한 개 남김"}, headers=headers)

    first = client.get(f"/reviews/{RECIPE_ID}/summary")
    assert first.status_code == 200
    assert first.json()["summary"] == "• 가짜 요약 첫째 줄\n• 가짜 요약 둘째 줄"
    assert call_count["n"] == 1

    # 후기 개수가 그대로면(리뷰 추가 없음) review_summaries 캐시를 그대로 재사용해야 하고,
    # LLM을 다시 부르면 안 된다.
    second = client.get(f"/reviews/{RECIPE_ID}/summary")
    assert second.status_code == 200
    assert second.json()["summary"] == first.json()["summary"]
    assert call_count["n"] == 1
