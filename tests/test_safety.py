"""
/safety/overview, /safety/check를 검증한다.

두 엔드포인트 모두 식약처 공공 API(safety_agent.get_all_recalls)를 실제로 호출하는데,
이 API는 이번 세션 검증 중에도 실제로 응답 없음(ReadTimeout)을 겪었을 만큼 불안정하다.
테스트에서 진짜 외부망을 타면 느리고 불안정하고 비용도 드니, safety_agent.get_all_recalls를
monkeypatch로 가짜 응답/예외로 바꿔서 라우터 계층의 분기(정상 집계, 503 처리)만 검증한다.

2026-07-19 추가: api/routers/safety.py가 get_all_recalls() 결과를 TTLCache로 10분간
재사용하도록 바뀌어서, 그 캐시(_recalls_cache)가 모듈 전역 상태로 남는다 - 그대로 두면
테스트 A의 monkeypatch 응답이 캐시에 남아 테스트 B에서도 재사용돼버린다. 매 테스트 전에
캐시를 비워서 각 테스트가 독립적으로 자신의 monkeypatch 응답을 실제로 타게 한다.
"""

from datetime import date, timedelta

import pytest
import requests

from api.routers import safety as safety_router
from src.agents import safety_agent


@pytest.fixture(autouse=True)
def _reset_recalls_cache():
    safety_router._recalls_cache.clear()
    yield


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _add_pantry(client, user_id: int, headers: dict, name: str, expiry_date: str | None = None):
    client.post(f"/pantry/{user_id}", json={"name": name, "expiry_date": expiry_date}, headers=headers)


def test_overview_empty_pantry_returns_zero_counts(client):
    user_id, headers = _signup(client, "u_safety_1")
    res = client.get("/safety/overview", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"total": 0, "warning_count": 0, "normal_count": 0, "items": []}


def test_overview_flags_recall_match_as_warning(client, monkeypatch):
    monkeypatch.setattr(
        safety_agent, "get_all_recalls",
        lambda: [{"PRDTNM": "OO식품 두부", "RTRVLPRVNS": "이물질 혼입"}],
    )
    user_id, headers = _signup(client, "u_safety_2")
    _add_pantry(client, user_id, headers, "두부")
    _add_pantry(client, user_id, headers, "당근")

    res = client.get("/safety/overview", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert body["warning_count"] == 1
    assert body["normal_count"] == 1

    by_name = {i["name"]: i for i in body["items"]}
    assert by_name["두부"]["status"] == "주의"
    assert "이물질 혼입" in by_name["두부"]["recall_summary"]
    assert by_name["당근"]["status"] == "정상"
    assert by_name["당근"]["recall_summary"] == ""


def test_overview_flags_soon_to_expire_item_as_warning(client, monkeypatch):
    monkeypatch.setattr(safety_agent, "get_all_recalls", lambda: [])
    user_id, headers = _signup(client, "u_safety_3")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    _add_pantry(client, user_id, headers, "계란", expiry_date=tomorrow)

    res = client.get("/safety/overview", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["warning_count"] == 1
    assert body["items"][0]["status"] == "주의"
    assert "임박" in body["items"][0]["expiry_status"]


def test_overview_returns_503_when_external_api_unavailable(client, monkeypatch):
    def _raise():
        raise requests.exceptions.ReadTimeout("simulated food-safety API outage")

    monkeypatch.setattr(safety_agent, "get_all_recalls", _raise)
    user_id, headers = _signup(client, "u_safety_4")
    _add_pantry(client, user_id, headers, "두부")

    res = client.get("/safety/overview", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 503
    assert "식약처" in res.json()["detail"]


def test_overview_reuses_cached_recalls_within_ttl(client, monkeypatch):
    call_count = {"n": 0}

    def _fake_recalls():
        call_count["n"] += 1
        return []

    monkeypatch.setattr(safety_agent, "get_all_recalls", _fake_recalls)
    user_id, headers = _signup(client, "u_safety_5")
    _add_pantry(client, user_id, headers, "두부")

    client.get("/safety/overview", params={"user_id": user_id}, headers=headers)
    client.get("/safety/overview", params={"user_id": user_id}, headers=headers)
    assert call_count["n"] == 1  # 두 번째 요청은 TTLCache가 재사용해서 실제 호출은 1번뿐


def test_overview_falls_back_to_last_success_when_api_fails(client, monkeypatch):
    monkeypatch.setattr(
        safety_agent, "get_all_recalls",
        lambda: [{"PRDTNM": "OO식품 두부", "RTRVLPRVNS": "이물질 혼입"}],
    )
    user_id, headers = _signup(client, "u_safety_6")
    _add_pantry(client, user_id, headers, "두부")

    first = client.get("/safety/overview", params={"user_id": user_id}, headers=headers)
    assert first.status_code == 200
    assert first.json()["warning_count"] == 1

    def _raise():
        raise requests.exceptions.ReadTimeout("simulated outage right after a success")

    monkeypatch.setattr(safety_agent, "get_all_recalls", _raise)
    second = client.get("/safety/overview", params={"user_id": user_id}, headers=headers)
    # 방금 API가 실패했어도, 직전 성공 응답이 캐시에 남아있어 503 대신 그 값을 그대로 쓴다.
    assert second.status_code == 200
    assert second.json()["warning_count"] == 1


def test_check_single_ingredient_saves_recall_note(client, monkeypatch):
    monkeypatch.setattr(
        safety_agent, "get_all_recalls",
        lambda: [{"PRDTNM": "OO식품 두부", "RTRVLPRVNS": "표시기준 위반"}],
    )
    res = client.post("/safety/check", json={"ingredient_name": "두부", "expiry_date": None})
    assert res.status_code == 200
    body = res.json()
    assert len(body["recall_matches"]) == 1
    assert body["saved_notes"] == 1
    assert body["expiry_status"] is None


def test_check_returns_503_when_external_api_unavailable(client, monkeypatch):
    def _raise():
        raise requests.exceptions.ConnectionError("simulated outage")

    monkeypatch.setattr(safety_agent, "get_all_recalls", _raise)
    res = client.post("/safety/check", json={"ingredient_name": "두부", "expiry_date": None})
    assert res.status_code == 503
