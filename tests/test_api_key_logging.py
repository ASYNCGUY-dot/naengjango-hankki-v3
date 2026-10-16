"""외부 API가 실패해도 인증 키가 출력(서버 로그)에 남지 않는다 (2026-10-16).

requests의 연결 오류·시간 초과 메시지에는 쿼리 문자열을 포함한 요청 주소 전체가 들어 있다
(실측: ConnectionError, ConnectTimeout 둘 다 메시지에 키가 들어 있었다). 공공데이터(식품영양성분)는
serviceKey를, 유튜브는 key를 쿼리로 보내는데, 실패하면 그 메시지를 그대로 출력하고 있었다.
KAMIS에서 같은 문제를 먼저 고쳤다(tests/test_price_matching.py의 인증값 보호 테스트).

가짜 키를 쓴다. 실제 키는 테스트에도 출력에도 나오지 않는다.
"""

import pytest
import requests

from src.agents import ingredient_agent, ingredient_catalog_agent, popular_recipe_agent, youtube_agent

FAKE_KEY = "FAKE-API-KEY-12345"
ERRORS = [
    requests.exceptions.ConnectionError,
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ReadTimeout,
]


def _raising_get(exc):
    """실제 requests처럼 쿼리를 담은 주소 전체를 메시지에 넣어 던진다."""
    def fake_get(url, params=None, timeout=None):
        query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
        raise exc(f"Max retries exceeded with url: {url}?{query}")
    return fake_get


def _logged(capsys) -> str:
    out = capsys.readouterr()
    return out.out + out.err


@pytest.mark.parametrize("exc", ERRORS)
def test_nutrition_lookup_failure_hides_the_key(monkeypatch, capsys, exc):
    monkeypatch.setattr(ingredient_agent, "API_KEY", FAKE_KEY)
    monkeypatch.setattr(ingredient_agent.requests, "get", _raising_get(exc))

    assert ingredient_agent.match_nutrition("두부") is None
    logged = _logged(capsys)
    assert FAKE_KEY not in logged
    assert "두부" in logged  # 무엇이 실패했는지는 남긴다


@pytest.mark.parametrize("exc", ERRORS)
def test_bulk_catalog_collect_failure_hides_the_key(monkeypatch, capsys, tmp_path, exc):
    monkeypatch.setattr(ingredient_catalog_agent, "API_KEY", FAKE_KEY)
    monkeypatch.setattr(ingredient_catalog_agent, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(
        ingredient_catalog_agent, "load_progress", lambda: {"last_completed_page": 0, "total_count": None},
    )
    monkeypatch.setattr(ingredient_catalog_agent, "save_progress", lambda progress: None)
    monkeypatch.setattr(ingredient_catalog_agent.requests, "get", _raising_get(exc))

    ingredient_catalog_agent.run_bulk_collect(max_pages_per_run=1)
    logged = _logged(capsys)
    assert FAKE_KEY not in logged
    assert "네트워크" in logged


@pytest.mark.parametrize("exc", ERRORS)
def test_popular_video_search_failure_hides_the_key(monkeypatch, capsys, exc):
    monkeypatch.setattr(popular_recipe_agent, "API_KEY", FAKE_KEY)
    monkeypatch.setattr(popular_recipe_agent.requests, "get", _raising_get(exc))

    assert popular_recipe_agent._search_videos("김치찌개") == []
    assert popular_recipe_agent._get_view_counts(["abc123"]) == {}
    logged = _logged(capsys)
    assert FAKE_KEY not in logged
    assert "실패" in logged


@pytest.mark.parametrize("exc", ERRORS)
def test_recipe_video_search_failure_hides_the_key(monkeypatch, capsys, exc):
    monkeypatch.setattr(youtube_agent, "API_KEY", FAKE_KEY)
    monkeypatch.setattr(youtube_agent.requests, "get", _raising_get(exc))

    assert youtube_agent.search_youtube_video("김치찌개") is None
    logged = _logged(capsys)
    assert FAKE_KEY not in logged
    assert "실패" in logged
